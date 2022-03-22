# h3-monkey-god

## Getting Started

This repo provides tools for converting rasters into the [H3](https://h3geo.org/) hexagon index. You can use it to create create H3 subsets of large rasters, using conversion functions to resample to lower resolution hexagons. It was designed for, but is not exclusively useful for, interacting with the [Malaria Atlas Project's friction surface](https://malariaatlas.org/research-project/accessibility-to-cities/). The `friction_h3_traversal` module provides least cost path and isochrone algorithms wrapped around H3 to calculate travel time distances from an origin using the friction surface.

## Setting up

The friction surface itself is sizeable, so you'll have to [download it](https://malariaatlas.org/geoserver/ows?service=CSW&version=2.0.1&request=DirectDownload&ResourceId=Explorer:2015_friction_surface_v1_Decompressed) yourself and place it in the `data` directory. As a helper, you can run `python get_data.py` from the CLI to fetch the data automatically.

### Installing

If you're going to interact with the friction surface itself rather than derived H3 outputs, you'll have to set up GDAL and install some additional processing libraries. GDAL and rasterio can be a pain to install and should be installed using binaries that aren't available via pip. See the [installation instructions in the rasterio documentation](https://rasterio.readthedocs.io/en/latest/installation.html) to install both GDAL and rasterio.

## Running the code

There are two primary use cases for this library:

### Hexagonifying a raster, like a friction surface:

The friction surface is great as a raster, but converting it to hexagons makes it easier to resample and write grid traversal algorithms outside of the Esri sphere. The sample code below will create a CSV of hexagon-value pairs in this repository's `OUTPUT_DIR` called `friction_surface.csv` (matching the input raster name) that is geographically constrained between the top left and bottom right point.

```python
import h3aster
import os
h3converter = h3raster.RasterH3Converter()
TOP_LEFT_POINT = (55.95, -137.85369)
BOTTOM_RIGHT_POINT = (11.7469, -63.27451)
friction_path = os.path.join(h3aster.DATA_DIR, "friction_surface.tif")
h3converter.create_h3_from_raster(
    friction_path,
    "min",
    TOP_LEFT_POINT,
    BOTTOM_RIGHT_POINT,
    conversion_func=h3converter.friction_cost_to_minutes,
)
```

### Calculating drive times

You can calculate drive time distances and isochrones using the `friction_h3_traversal` module.

To calculate the drive time between two points:

```python
import friction_h3_traversal as traversal
start = (43.79916, -79.336)  # Set your start location
end = (42.50625, -77.027)  # Set your end location
traversal.calculate_travel_time(start, end)
```

To create a 90 minute drive time isochrone:

```python
import friction_h3_traversal as traversal
start = (43.79916, -79.336)  # Set your start location
end = (42.50625, -77.027)  # Set your end location
traversal.calculate_travel_time(start, end, 90)
```

## Visualizing outputs

[kepler.gl](https://kepler.gl/) is an excellent tool for visualizing outputs and has built-in support for H3.
