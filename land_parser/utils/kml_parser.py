import xml.etree.ElementTree as ET
import re
import logging
from typing import Dict, List, Tuple, Optional, Any
from decimal import Decimal
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
import math
import functools
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

logger = logging.getLogger(__name__)

class KMLParser:
    """
    Comprehensive KML parser for extracting land parcel information
    """
    
    def __init__(self):
        self.namespaces = {
            'kml': 'http://www.opengis.net/kml/2.2',
            'gx': 'http://www.google.com/kml/ext/2.2'
        }
        self.supported_geometries = ['Point', 'LineString', 'Polygon', 'MultiGeometry']
        
        # Patterns for extracting data from KML
        self.kitta_pattern = re.compile(r'kitta[:\s]*([A-Za-z0-9\-_]+)', re.IGNORECASE)
        self.owner_pattern = re.compile(r'owner[:\s]*([A-Za-z\s]+)', re.IGNORECASE)
        self.area_pattern = re.compile(r'area[:\s]*([0-9,\.]+)', re.IGNORECASE)
        
        # Performance optimizations
        self._coordinate_cache = {}
        self._area_cache = {}
        self._parsing_cache = {}
        self.max_workers = 4  # Number of threads for parallel processing
        
    def parse_kml(self, kml_content: str) -> Dict[str, Any]:
        """
        Main parsing function that extracts land parcel data from KML
        
        Args:
            kml_content: Raw KML content as string
            
        Returns:
            Dict containing parsed data, errors, and statistics
        """
        start_time = time.time()
        
        # Check cache first
        content_hash = hash(kml_content)
        if content_hash in self._parsing_cache:
            logger.info("Using cached parsing result")
            return self._parsing_cache[content_hash]
        
        result = {
            'success': False,
            'parcels': [],
            'total_parcels': 0,
            'total_area': 0.0,
            'errors': [],
            'warnings': [],
            'statistics': {
                'placemarks_found': 0,
                'polygons_found': 0,
                'points_found': 0,
                'linestrings_found': 0,
                'parcels_with_kitta': 0,
                'parcels_with_owner': 0,
                'parcels_with_area': 0
            },
            'performance': {
                'parsing_time': 0,
                'total_placemarks': 0
            }
        }
        
        try:
            # Parse XML
            root = ET.fromstring(kml_content)
            
            # Find all Placemarks
            placemarks = self._find_placemarks(root)
            result['statistics']['placemarks_found'] = len(placemarks)
            result['performance']['total_placemarks'] = len(placemarks)
            
            if not placemarks:
                result['errors'].append("No Placemark elements found in KML")
                return result
            
            # Use parallel processing for large datasets
            if len(placemarks) > 50:
                parcels = self._process_placemarks_parallel(placemarks)
            else:
                parcels = self._process_placemarks_sequential(placemarks)
            
            # Process results
            for parcel_data in parcels:
                if parcel_data:
                    result['parcels'].append(parcel_data)
                    result['total_area'] += parcel_data.get('area', 0)
                    
                    # Update statistics
                    if parcel_data.get('kitta_number'):
                        result['statistics']['parcels_with_kitta'] += 1
                    if parcel_data.get('owner_name'):
                        result['statistics']['parcels_with_owner'] += 1
                    if parcel_data.get('area'):
                        result['statistics']['parcels_with_area'] += 1
            
            result['total_parcels'] = len(result['parcels'])
            result['success'] = result['total_parcels'] > 0
            
            if not result['success']:
                result['warnings'].append("No valid land parcels found in KML")
            
            # Calculate performance metrics
            result['performance']['parsing_time'] = time.time() - start_time
            
            # Cache the result
            self._parsing_cache[content_hash] = result
            
            # Limit cache size
            if len(self._parsing_cache) > 100:
                # Remove oldest entries
                oldest_keys = list(self._parsing_cache.keys())[:20]
                for key in oldest_keys:
                    del self._parsing_cache[key]
                
        except ET.ParseError as e:
            result['errors'].append(f"XML parsing error: {str(e)}")
        except Exception as e:
            result['errors'].append(f"Unexpected error during parsing: {str(e)}")
            logger.error(f"KML parsing error: {e}")
        
        return result
    
    def _find_placemarks(self, root: ET.Element) -> List[ET.Element]:
        """Find all Placemark elements regardless of namespace"""
        placemarks = []
        
        # Try different namespace patterns
        patterns = [
            './/{http://www.opengis.net/kml/2.2}Placemark',
            './/Placemark',
            './/kml:Placemark',
            './/*[local-name()="Placemark"]'
        ]
        
        for pattern in patterns:
            try:
                found = root.findall(pattern)
                if found:
                    placemarks.extend(found)
            except Exception:
                continue
        
        # Remove duplicates while preserving order
        seen = set()
        unique_placemarks = []
        for pm in placemarks:
            if id(pm) not in seen:
                seen.add(id(pm))
                unique_placemarks.append(pm)
        
        return unique_placemarks
    
    def _process_placemarks_sequential(self, placemarks: List[ET.Element]) -> List[Optional[Dict[str, Any]]]:
        """Process placemarks sequentially (for small datasets)"""
        return [self._extract_parcel_data(placemark) for placemark in placemarks]
    
    def _process_placemarks_parallel(self, placemarks: List[ET.Element]) -> List[Optional[Dict[str, Any]]]:
        """Process placemarks in parallel (for large datasets)"""
        parcels = [None] * len(placemarks)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_index = {
                executor.submit(self._extract_parcel_data, placemark): i 
                for i, placemark in enumerate(placemarks)
            }
            
            # Collect results
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    parcels[index] = future.result()
                except Exception as e:
                    logger.error(f"Error processing placemark {index}: {e}")
                    parcels[index] = None
        
        return parcels
    
    def _extract_parcel_data(self, placemark: ET.Element) -> Optional[Dict[str, Any]]:
        """
        Extract land parcel data from a Placemark element
        
        Args:
            placemark: Placemark XML element
            
        Returns:
            Dict containing parcel data or None if invalid
        """
        try:
            # Extract basic information
            name = self._get_element_text(placemark, 'name')
            description = self._get_element_text(placemark, 'description')
            
            # Extract geometry
            geometry_data = self._extract_geometry(placemark)
            if not geometry_data:
                return None
            
            # Extract parcel information
            kitta_number = self._extract_kitta_number(name, description)
            owner_name = self._extract_owner_name(name, description)
            
            # Calculate area
            area = self._calculate_area(geometry_data['coordinates'], geometry_data['type'])
            
            # Create parcel data
            parcel_data = {
                'kitta_number': kitta_number or 'PARCEL',
                'owner_name': owner_name or 'Unknown Owner',
                'area': area,
                'area_hectares': area / 10000 if area else 0,  # Convert to hectares
                'coordinates': geometry_data['coordinates'],
                'geometry_type': geometry_data['type'],
                'name': name,
                'description': description,
                'center_point': self._calculate_center(geometry_data['coordinates'], geometry_data['type'])
            }
            
            return parcel_data
            
        except Exception as e:
            logger.error(f"Error extracting parcel data: {e}")
            return None
    
    def _extract_geometry(self, placemark: ET.Element) -> Optional[Dict[str, Any]]:
        """Extract geometry data from Placemark"""
        geometry_patterns = {
            'Point': [
                './/{http://www.opengis.net/kml/2.2}Point',
                './/Point',
                './/kml:Point'
            ],
            'LineString': [
                './/{http://www.opengis.net/kml/2.2}LineString',
                './/LineString',
                './/kml:LineString'
            ],
            'Polygon': [
                './/{http://www.opengis.net/kml/2.2}Polygon',
                './/Polygon',
                './/kml:Polygon'
            ],
            'MultiGeometry': [
                './/{http://www.opengis.net/kml/2.2}MultiGeometry',
                './/MultiGeometry',
                './/kml:MultiGeometry'
            ]
        }
        
        for geom_type, patterns in geometry_patterns.items():
            for pattern in patterns:
                try:
                    geom_elem = placemark.find(pattern)
                    if geom_elem is not None:
                        coords = self._extract_coordinates(geom_elem, geom_type)
                        if coords:
                            return {
                                'type': geom_type,
                                'coordinates': coords
                            }
                except Exception:
                    continue
        
        return None
    
    def _extract_coordinates(self, geometry_elem: ET.Element, geom_type: str) -> Optional[List[List[float]]]:
        """Extract coordinates from geometry element"""
        coord_patterns = [
            './/{http://www.opengis.net/kml/2.2}coordinates',
            './/coordinates',
            './/kml:coordinates'
        ]
        
        for pattern in coord_patterns:
            try:
                coords_elem = geometry_elem.find(pattern)
                if coords_elem is not None and coords_elem.text:
                    return self._parse_coordinate_string(coords_elem.text, geom_type)
            except Exception:
                continue
        
        return None
    
    def _parse_coordinate_string(self, coord_text: str, geom_type: str) -> List[List[float]]:
        """Parse coordinate string into list of [lon, lat, alt] coordinates"""
        coordinates = []
        
        # Split by whitespace and process each coordinate
        coord_pairs = coord_text.strip().split()
        
        for coord_pair in coord_pairs:
            parts = coord_pair.split(',')
            if len(parts) >= 2:
                try:
                    lon = float(parts[0].strip())
                    lat = float(parts[1].strip())
                    alt = float(parts[2].strip()) if len(parts) > 2 else 0.0
                    
                    # Validate coordinate ranges
                    if -180 <= lon <= 180 and -90 <= lat <= 90:
                        coordinates.append([lon, lat, alt])
                except ValueError:
                    continue
        
        return coordinates
    
    def _extract_kitta_number(self, name: str, description: str) -> Optional[str]:
        """Extract kitta number from name or description"""
        # Try name first
        if name:
            match = self.kitta_pattern.search(name)
            if match:
                return match.group(1).strip()
        
        # Try description
        if description:
            match = self.kitta_pattern.search(description)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_owner_name(self, name: str, description: str) -> Optional[str]:
        """Extract owner name from name or description"""
        # Try name first
        if name:
            match = self.owner_pattern.search(name)
            if match:
                return match.group(1).strip()
        
        # Try description
        if description:
            match = self.owner_pattern.search(description)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _calculate_area(self, coordinates: List[List[float]], geom_type: str) -> float:
        """
        Calculate area in square meters using Shapely with caching
        
        Args:
            coordinates: List of [lon, lat, alt] coordinates
            geom_type: Type of geometry (Point, LineString, Polygon, MultiGeometry)
            
        Returns:
            Area in square meters
        """
        # Create cache key
        coord_hash = hash(str(coordinates) + geom_type)
        if coord_hash in self._area_cache:
            return self._area_cache[coord_hash]
        
        try:
            if geom_type == 'Polygon' and len(coordinates) >= 3:
                # Create polygon from coordinates
                polygon = Polygon(coordinates)
                if polygon.is_valid:
                    # Calculate area in square meters (approximate)
                    # This is a simplified calculation - for precise areas,
                    # you'd need to use a proper geodetic library
                    area_m2 = self._calculate_geodetic_area(coordinates)
                    self._area_cache[coord_hash] = area_m2
                    return area_m2
            
            elif geom_type == 'MultiGeometry':
                # Handle multiple geometries
                total_area = 0.0
                for geom_coords in coordinates:
                    if len(geom_coords) >= 3:
                        area_m2 = self._calculate_geodetic_area(geom_coords)
                        total_area += area_m2
                self._area_cache[coord_hash] = total_area
                return total_area
            
            elif geom_type == 'Point':
                # For points, return a small default area
                area = 1.0
                self._area_cache[coord_hash] = area
                return area
            
            elif geom_type == 'LineString':
                # For lines, calculate approximate area based on buffer
                if len(coordinates) >= 2:
                    from shapely.geometry import LineString
                    line = LineString(coordinates)
                    buffer_distance = 0.001  # Small buffer
                    buffered = line.buffer(buffer_distance)
                    # Convert buffered polygon to coordinates and calculate area
                    if hasattr(buffered, 'exterior'):
                        coords = list(buffered.exterior.coords)
                        area = self._calculate_geodetic_area(coords)
                        self._area_cache[coord_hash] = area
                        return area
                    area = 0.0
                    self._area_cache[coord_hash] = area
                    return area
            
            # Default case
            area = 0.0
            self._area_cache[coord_hash] = area
            
            # Limit cache size
            if len(self._area_cache) > 1000:
                # Remove oldest entries
                oldest_keys = list(self._area_cache.keys())[:200]
                for key in oldest_keys:
                    del self._area_cache[key]
            
            return area
            
        except Exception as e:
            logger.error(f"Error calculating area: {e}")
            return 0.0
    
    def _calculate_geodetic_area(self, coordinates: List[List[float]]) -> float:
        """
        Calculate approximate geodetic area using Haversine formula
        This is a simplified calculation - for production use, consider using
        libraries like pyproj or geopy for more accurate calculations
        """
        if len(coordinates) < 3:
            return 0.0
        
        try:
            # Convert to radians
            coords_rad = [(math.radians(lon), math.radians(lat)) for lon, lat, _ in coordinates]
            
            # Calculate area using shoelace formula with spherical correction
            area = 0.0
            n = len(coords_rad)
            
            for i in range(n):
                j = (i + 1) % n
                area += coords_rad[i][0] * coords_rad[j][1]
                area -= coords_rad[j][0] * coords_rad[i][1]
            
            area = abs(area) / 2.0
            
            # Convert to square meters (approximate)
            # Earth's radius in meters
            earth_radius = 6371000
            area_m2 = area * earth_radius * earth_radius
            
            return area_m2
            
        except Exception as e:
            logger.error(f"Error in geodetic area calculation: {e}")
            return 0.0
    
    def _calculate_center(self, coordinates: List[List[float]], geom_type: str) -> Optional[Tuple[float, float]]:
        """Calculate center point of geometry"""
        if not coordinates:
            return None
        
        try:
            if geom_type == 'Point':
                return (coordinates[0][0], coordinates[0][1])
            
            elif geom_type in ['LineString', 'Polygon']:
                # Calculate centroid
                lons = [coord[0] for coord in coordinates]
                lats = [coord[1] for coord in coordinates]
                return (sum(lons) / len(lons), sum(lats) / len(lats))
            
        except Exception as e:
            logger.error(f"Error calculating center: {e}")
        
        return None
    
    def _get_element_text(self, parent: ET.Element, tag_name: str) -> str:
        """Get text content of an element with various namespace patterns"""
        patterns = [
            f'.//{self.namespaces["kml"]}{tag_name}',
            f'.//{tag_name}',
            f'.//kml:{tag_name}'
        ]
        
        for pattern in patterns:
            try:
                elem = parent.find(pattern)
                if elem is not None and elem.text:
                    return elem.text.strip()
            except Exception:
                continue
        
        return ""

# Global parser instance
kml_parser = KMLParser() 