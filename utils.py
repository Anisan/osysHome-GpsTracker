import math

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the distance between two coordinates using the Haversine formula.

    Args:
        lat1 (float): Latitude of the first coordinate
        lon1 (float): Longitude of the first coordinate
        lat2 (float): Latitude of the second coordinate
        lon2 (float): Longitude of the second coordinate

    Returns:
        float: Distance between the two coordinates in meters
    """
    R = 6371  # Radius of the Earth in kilometers

    # Convert coordinates to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Calculate the differences between the coordinates
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    # Calculate the Haversine formula
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # Calculate the distance
    distance = R * c

    return distance * 1000

def in_location(lat1: float, lon1: float, lat2: float, lon2: float, range:float) -> bool:
    """
    Check if a location is within a certain range of another location.
    The range is given in kilometers.
    Args:
        lat1 (float): Latitude of the first coordinate
        lon1 (float): Longitude of the first coordinate
        lat2 (float): Latitude of the second coordinate
        lon2 (float): Longitude of the second coordinate
        range (float): Range in meters

    Returns:
        bool: True if the location is within the range, False otherwise
    """
    distance = calculate_distance(lat1, lon1, lat2, lon2)
    return distance < range
