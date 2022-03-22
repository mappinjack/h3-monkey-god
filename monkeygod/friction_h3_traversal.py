# -*- coding: utf-8 -*-
"""This module provides tools to calculate drive time distances and drive 
time isochrones using H3 and a friction surface.

Example:
    The easiest way to execute this code is via command line from within
    a configured virtual environment (see README for setup instructions)::

        $ python friction_h3_traversal.py
    
or by importing the module and running :func:`~calculate_travel_time`:

        >>> import friction_h3_traversal
        >>> friction_h3_traversal.calculate_travel_time((43.79916, -79.336),  (42.50625, -77.027))
        (2412341, 36.7)

"""

import os
import pathlib
import functools
import time
from datetime import datetime

import h3

import heapq
import pandas as pd

DATA_DIR = os.path.join(pathlib.Path(__file__).parent.absolute(), "data")


def timer(func):
    @functools.wraps(func)
    def wrapper_timer(*args, **kwargs):
        tic = time.perf_counter()
        value = func(*args, **kwargs)
        toc = time.perf_counter()
        elapsed_time = toc - tic
        print(f"Elapsed time for {str(func)}: {elapsed_time:0.4f} seconds")
        return value

    return wrapper_timer


def get_travel_time_hexes_from_csv(file_path="friction_surface.gz"):
    """Load a DataFrame of hexagons with their associated traversal costs

    A prerequisite for this is to have pre-calculated the friction surface
    into an H3 hexagon cost grid. See :func:`~friction_to_h3.create_h3_csv_from_friction_surface`

    Args:
        file_path (str): H3 friction surface file name. File expected to be in ``DATA_DIR``

    Returns:
        dict: ``{h3_id: {"cost": 10}}``
    """
    file_path = os.path.join(DATA_DIR, file_path)
    return pd.read_csv(file_path, index_col="hex").to_dict("index")


class H3CostGraph:
    """Graph data structure for traversing hexagons"""

    def __init__(self):
        self.edges = {}
        self.costs = get_travel_time_hexes_from_csv()

    def neighbors(self, h):
        return h3.hex_range(h, 1)

    def cost(self, current, next):
        """The default time to traverse a hexagon is 20 minutes. Beware.

        Future implementations of this can be directioned and include the
        "next" hexagon by calculating costs for each edge of a hexagon, rather
        than assuming uniform travel across it"""
        return self.costs.get(current, {}).get("value", 20)


class PriorityQueue:
    """Priority queue data structure for search algorithms"""

    def __init__(self):
        self.elements = []

    def empty(self) -> bool:
        return not self.elements

    def put(self, item, priority: float):
        heapq.heappush(self.elements, (priority, item))

    def get(self):
        return heapq.heappop(self.elements)[1]


# @timer
def dijkstra_search(graph, start, hex_goal=None, distance_goal=None):
    """Use Dijkstra's search to traverse hexagons between a starting point and an end goal.

    One of ``hex_goal`` or ``distance_goal`` must be used as a goal for the search.
    A ``hex_goal`` goal will calculate a least cost path between the starting point and
    the goal. A ``distance_goal`` will calculate an isochrone of hexes up to the goal
    originating from the start location.

    Heavy inspiration from: https://www.redblobgames.com/pathfinding/a-star/implementation.html#python-dijkstra

    Args:
        graph (H3CostGraph): an H3CostGraph object containing travel times
        start (tuple): Lat/lon pair of driving origin
        hex_goal (tuple): Lat/lon pair of driving destination
        distance_goal (int): Maximum number of minutes that when reached, will exit search

    Returns:
        tuple: came_from (dict), cost_so_far (dict)

        ``came_from`` is a dict of ``{hex: next_hex}``
        ``cost_so_far`` is a dict of ``{hex: cumulative_cost_so_far}``

    """

    assert hex_goal or distance_goal, "There must be a goal for the search algorithm"
    frontier = PriorityQueue()
    frontier.put(start, 0)
    came_from = {}
    cost_so_far = {}
    came_from[start] = None
    cost_so_far[start] = 0

    while not frontier.empty():
        current = frontier.get()

        if hex_goal is not None and current == hex_goal:
            break

        for next in graph.neighbors(current):
            new_cost = cost_so_far[current] + graph.cost(current, next)
            if next not in cost_so_far or new_cost < cost_so_far[next]:
                cost_so_far[next] = new_cost
                came_from[next] = current
                priority = new_cost
                if distance_goal is not None and priority >= distance_goal:
                    continue
                frontier.put(next, priority)

    return came_from, cost_so_far


@timer
def reconstruct_path(came_from, cost_so_far, start, goal):
    """Create a least cost path from :func:`~dijkstra_search` output

    Args:
        came_from (dict): Result of :func:`~dijkstra_search` containing traversal paths
        cost_so_far (dict): Result of :func:`~dijkstra_search` containing traversal costs
        start (str): H3 index of starting point
        goal (str): H3 index of search goal

    Returns:
        dict: Dictionary of hexagons with cost so far as value"""

    current = goal
    path = {}
    while current != start:
        cost = cost_so_far.get(current, 0)
        path[current] = cost
        current = came_from[current]
    path[start] = 0
    return path


temp_df_cache = {}
g = H3CostGraph()


def calculate_travel_time(
    start, hex_goal, distance_goal=3000, hex_res=6, temp_df_cache=temp_df_cache
):
    """Calculate drive time and intervening population.

    This function is caches drive time isochrones in the
    ``data`` folder, so the distance only needs to
    be calculated once.

    .. warning::
        Increasing the distance_goal increases the run time exponentially

    Args:
        start (tuple): Lat/lon pair of driving origin
        hex_goal (tuple): Lat/lon pair of driving destination
        distance_goal (int): Distance in minutes from start to calculate drive time
        hex_res (int): H3 resolution

    Returns:
        tuple: population (int), distance in minutes (float)
    """

    start_hex = h3.geo_to_h3(start[0], start[1], hex_res)
    hex_goal = h3.geo_to_h3(hex_goal[0], hex_goal[1], hex_res)
    iso_path = os.path.join(DATA_DIR, f"hex_isochrone_{start_hex}.gz")
    lcp_path = os.path.join(DATA_DIR, f"hex_path_{start_hex}.gz")
    s = datetime.utcnow()
    # TODO accommodate both hex and distance goals
    came_from, cost_so_far = dijkstra_search(g, start_hex, hex_goal=hex_goal)
    
    print(f"Search took {(datetime.utcnow() - s).total_seconds()} seconds")

    df = pd.DataFrame.from_dict(data=cost_so_far, orient="index").reset_index()
    df.columns = ["hex", "cost"]
    df = df[["hex", "cost"]]
    df["origin"] = start_hex
    df.to_csv(iso_path, header=True, index=False, compression="gzip")
    temp_df_cache.clear()
    temp_df_cache[iso_path] = df
    
    path = reconstruct_path(came_from, cost_so_far, start_hex, hex_goal)
    path_df = pd.DataFrame.from_dict(data=path, orient="index").reset_index()
    path_df.columns = ["hex", "cost"]
    path_df = path_df[["hex", "cost"]]
    path_df["origin"] = start_hex
    path_df.to_csv(lcp_path, header=True, index=False, compression="gzip")
    

    # Optimization to avoid repeatedly opening (and unzipping) raster from disk
    #   If your input Origins are sorted, this will considerably speed up your searches
    if temp_df_cache.get(iso_path) is not None:
        iso_df = temp_df_cache.get(iso_path)
    else:
        iso_df = pd.read_csv(iso_path)
        temp_df_cache.clear()
        temp_df_cache[iso_path] = iso_df

    try:
        cost_to_dest = list(iso_df[iso_df["hex"] == hex_goal]["cost"])[0]

    except IndexError:
        cost_to_dest = distance_goal

    return cost_to_dest


if __name__ == "__main__":
    start = (15.462, -87.934)  # Set your start location
    end = (15.350, -84.900)  # Set your end location
    print(calculate_travel_time(start, end, hex_res=7))
