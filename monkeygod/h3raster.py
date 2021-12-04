import os
import pathlib
from math import floor, ceil
import h3
import rasterio
from rasterio.windows import Window
from pyproj import Proj
import pandas as pd
from zipfile import ZipFile
import boto3
from collections import namedtuple
import ntpath

DATA_DIR = os.path.join(pathlib.Path(__file__).parent.absolute().parent, "data")
OUTPUT_DIR = os.path.join(DATA_DIR, "outputs")


class DataGetter:
    def __init__(self):
        self.s3 = boto3.resource("s3")
        self._check_data_dir()

    def download_file(self, bucket, key):
        file_name = key.split("/")[-1]
        file_path = os.path.join(DATA_DIR, file_name)
        if os.path.exists(file_name):
            return "File already exists"
        self.s3.Bucket(bucket).download_file(key, file_path)

        if file_name.endswith(".zip"):
            with ZipFile(file_path, "r") as zip_ref:
                zip_ref.extractall(DATA_DIR)

    @staticmethod
    def _check_data_dir():
        if not os.path.exists(DATA_DIR):
            os.mkdir(DATA_DIR)


HexStore = namedtuple("HexStore", "value count")


class RasterH3Converter:
    """Class to convert rasters to H3 CSVs"""

    def __init__(self):
        pass

    @staticmethod
    def lat_lon_to_window(top_left, bottom_right, dataset):
        """Convert coordinates to a window for windowed raster reading

        Args:
            top_left: tuple of (lat, lon) for top left of window
            top_right: tuple of (lat, lon) for bottom right of window
            dataset: Rasterio dataset, result of rasterio.open

        Returns:
            rasterio.windows.Window"""

        p = Proj(dataset.crs)
        t = dataset.transform
        xmin, ymin = p(top_left[1], bottom_right[0])
        xmax, ymax = p(bottom_right[1], top_left[0])
        col_min, row_min = ~t * (xmin, ymin)
        col_max, row_max = ~t * (xmax, ymax)
        return Window.from_slices(
            rows=(floor(row_max), ceil(row_min)), cols=(floor(col_min), ceil(col_max))
        )

    @staticmethod
    def friction_cost_to_minutes(cost, h3_res=6):
        """Input is "minutes required to travel one meter"

        Args:
            cost: int/float of a friction cost
            h3_res: hexagon resolution
        Returns:
            Friction cost in minutes per hexagon"""
        # TODO should use: exactEdgeLengthM#
        edge_length = h3.edge_length(h3_res, unit="m")
        hex_diameter = edge_length * 2
        # cost /= 100 # Friction surface is 100 Xed
        # cost *= 1000 # Minutes per km
        return cost * hex_diameter / 100  # Minutes to cross hex #TODO

    @staticmethod
    def pop_density_to_pop(density, h3_res=6):
        """Swap from density to population"""
        area = h3.hex_area(h3_res, unit="km^2")
        return density * area

    def create_h3_from_raster(
        self,
        in_file,
        method,
        top_left=None,
        bottom_right=None,
        conversion_func=None,
        h3_res=6,
        break_val=None,
    ):
        """Create a CSV of H3 IDs with friction values from the friction raster

        Generally, outputs will be too large to process the entire surface in one go. It may need
        to be divided up, or if you're only working in a particular study area, you can calculate
        the H3 grid for only what you need by using the top_left and bottom_right parameters.

        If you have a hex resolution that's smaller than 1km (>= 8), there will be holes in
        your output grid.

        For the MAP friction surface, exagon values are represented in "minutes required to
        travel one meter" within the hexagon. The input raster is 1kmx1km resolution.

        Args:
            in_file: File path to input raster
            method: Resampling method, one of "sum", "avg", "max", "min" to convert cells to H3
            top_left (tuple): (lat, lon) for top left of window, if you only want to process a subset of the raster
            bottom_right (tuple): (lat, lon) for bottom right of window, if you only want to process a subset of the raster
            conversion_func (func): Function to convert resampled hexagon to a final value, if desired
            h3_res (int): H3 resolution to use
            break_val (int): Approximate number of cells to process. Generally
                                used for testing to exit early when processing a large study area.

        Returns:
            None: Writes a CSV to the OUTPUT_DIR, matching `in_file` file name."""

        hexes = {}
        cnt = 0

        input_file_name = ntpath.split(in_file)[-1]
        output_file_name = input_file_name.split(".")[0] + ".gz"
        output_file_path = os.path.join(OUTPUT_DIR, output_file_name)
        src = rasterio.open(in_file)
        window = None
        if top_left and bottom_right:
            window = self.lat_lon_to_window(top_left, bottom_right, src)
        for x, row in enumerate(src.read(1, window=window)):
            for y, new_val in enumerate(row):
                lon, lat = src.xy(x + window.row_off, y + window.col_off)
                h = h3.geo_to_h3(lat, lon, h3_res)
                existing_val = hexes.get(h)
                if existing_val is None:
                    existing_val = HexStore(None, 0)
                if method == "max":
                    if existing_val.value is None or existing_val.value < new_val:
                        hexes[h] = HexStore(new_val, 1)
                elif method == "min":
                    if existing_val.value is None or existing_val.value > new_val:
                        hexes[h] = HexStore(new_val, 1)
                elif method == "avg":
                    if existing_val.value is None or new_val < 0.000000000001:
                        new_val = 0
                    if existing_val.value is None or existing_val.count == 0:
                        hexes[h] = HexStore(new_val, 1)
                    else:
                        new_val = ((existing_val.value * existing_val.count) + new_val) / (
                            existing_val.count + 1
                        )
                        hexes[h] = HexStore(new_val, existing_val.count + 1)
                elif method == "sum":
                    val = existing_val.value or 0
                    hexes[h] = (val + new_val, existing_val.count + 1)
                else:
                    raise NotImplementedError("Unknown method")

                if cnt % 100000 == 0:
                    print(f"Processed {cnt} rows")
                cnt += 1
            if break_val and cnt > break_val:
                break

        df = pd.DataFrame.from_dict(data=hexes, orient="index").reset_index()
        df.columns = ["hex", "value", "count"]
        df["value"] = df["value"].apply(conversion_func)
        df[["hex", "value"]].to_csv(output_file_path, header=True, index=False, compression="gzip")
        print(f"Results written to {output_file_path}")


if __name__ == "__main__":
    # TOP_LEFT_POINT = (55.95, -137.85369)
    # BOTTOM_RIGHT_POINT = (11.7469, -63.27451)
    h3converter = RasterH3Converter()
    TOP_LEFT_POINT = (48.95, -88.85369)
    BOTTOM_RIGHT_POINT = (33.7469, -69.27451)
    friction_path = os.path.join(DATA_DIR, "GLOBAL_FRICTION100.tif")
    h3converter.create_h3_from_raster(
        friction_path,
        "min",
        TOP_LEFT_POINT,
        BOTTOM_RIGHT_POINT,
        conversion_func=h3converter.friction_cost_to_minutes,
    )
