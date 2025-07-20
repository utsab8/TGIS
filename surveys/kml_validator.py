import xml.etree.ElementTree as ET
import re
import logging
from typing import Dict, List, Tuple, Optional, Any

logger = logging.getLogger(__name__)

class KMLValidator:
    """Comprehensive KML validation and parsing utility"""
    
    def __init__(self):
        self.namespaces = {
            'kml': 'http://www.opengis.net/kml/2.2',
            'gx': 'http://www.google.com/kml/ext/2.2'
        }
        self.supported_geometries = ['Point', 'LineString', 'Polygon', 'MultiGeometry']
        self.coordinate_pattern = re.compile(r'^\s*([+-]?\d+\.?\d*)\s*,\s*([+-]?\d+\.?\d*)(?:\s*,\s*([+-]?\d+\.?\d*))?\s*$')
    
    def validate_kml_geometry(self, kml_content: str) -> Dict[str, Any]:
        """
        Comprehensive KML validation function that returns detailed diagnostic info
        
        Returns:
            Dict containing validation results, errors, warnings, and suggestions
        """
        result = {
            'is_valid': False,
            'features_found': 0,
            'geometries_found': 0,
            'coordinates_found': 0,
            'errors': [],
            'warnings': [],
            'suggestions': [],
            'parsed_features': [],
            'coordinate_issues': [],
            'structure_analysis': {}
        }
        
        try:
            # Parse XML
            root = ET.fromstring(kml_content)
            
            # Check for KML root element
            if root.tag not in ['kml', '{http://www.opengis.net/kml/2.2}kml']:
                result['errors'].append("Root element is not 'kml' - invalid KML structure")
                return result
            
            # Analyze structure
            result['structure_analysis'] = self._analyze_structure(root)
            
            # Find all Placemarks
            placemarks = self._find_placemarks(root)
            result['features_found'] = len(placemarks)
            
            if not placemarks:
                result['errors'].append("No Placemark elements found in KML")
                result['suggestions'].append("Ensure your KML contains <Placemark> elements with geometry")
                return result
            
            # Process each Placemark
            for i, placemark in enumerate(placemarks):
                feature_info = self._analyze_placemark(placemark, i)
                result['parsed_features'].append(feature_info)
                
                if feature_info['has_geometry']:
                    result['geometries_found'] += 1
                
                if feature_info['coordinates_found']:
                    result['coordinates_found'] += feature_info['coordinates_found']
                
                # Collect errors and warnings
                result['errors'].extend(feature_info['errors'])
                result['warnings'].extend(feature_info['warnings'])
                result['coordinate_issues'].extend(feature_info['coordinate_issues'])
            
            # Determine overall validity
            result['is_valid'] = (
                result['features_found'] > 0 and 
                result['geometries_found'] > 0 and 
                result['coordinates_found'] > 0 and
                len(result['errors']) == 0
            )
            
            # Generate suggestions based on analysis
            self._generate_suggestions(result)
            
        except ET.ParseError as e:
            result['errors'].append(f"XML parsing error: {str(e)}")
            result['suggestions'].append("Check if the KML file is valid XML")
        except Exception as e:
            result['errors'].append(f"Unexpected error during validation: {str(e)}")
            logger.error(f"KML validation error: {e}")
        
        return result
    
    def _analyze_structure(self, root: ET.Element) -> Dict[str, Any]:
        """Analyze the overall KML structure"""
        structure = {
            'has_document': False,
            'has_folder': False,
            'document_count': 0,
            'folder_count': 0,
            'placemark_count': 0,
            'geometry_types': set(),
            'namespaces_used': set()
        }
        
        # Check for namespaces
        for prefix, uri in root.nsmap.items() if hasattr(root, 'nsmap') else []:
            structure['namespaces_used'].add(prefix)
        
        # Count elements
        for elem in root.iter():
            tag = elem.tag
            if 'Document' in tag:
                structure['has_document'] = True
                structure['document_count'] += 1
            elif 'Folder' in tag:
                structure['has_folder'] = True
                structure['folder_count'] += 1
            elif 'Placemark' in tag:
                structure['placemark_count'] += 1
            elif any(geom in tag for geom in self.supported_geometries):
                geom_type = tag.split('}')[-1] if '}' in tag else tag
                structure['geometry_types'].add(geom_type)
        
        return structure
    
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
    
    def _analyze_placemark(self, placemark: ET.Element, index: int) -> Dict[str, Any]:
        """Analyze a single Placemark element"""
        feature_info = {
            'index': index,
            'name': self._get_element_text(placemark, 'name'),
            'description': self._get_element_text(placemark, 'description'),
            'has_geometry': False,
            'geometry_type': None,
            'coordinates_found': 0,
            'coordinates_valid': 0,
            'errors': [],
            'warnings': [],
            'coordinate_issues': [],
            'raw_coordinates': [],
            'parsed_coordinates': []
        }
        
        # Find geometry elements
        geometry = self._find_geometry(placemark)
        if geometry:
            feature_info['has_geometry'] = True
            feature_info['geometry_type'] = geometry['type']
            
            # Analyze coordinates
            coord_analysis = self._analyze_coordinates(geometry['coordinates'])
            feature_info.update(coord_analysis)
        
        else:
            feature_info['errors'].append(f"Placemark '{feature_info['name']}' has no geometry elements")
            feature_info['suggestions'].append("Add Point, LineString, or Polygon geometry to this Placemark")
        
        return feature_info
    
    def _find_geometry(self, placemark: ET.Element) -> Optional[Dict[str, Any]]:
        """Find geometry elements in a Placemark"""
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
                        coords_elem = self._find_coordinates_element(geom_elem, geom_type)
                        if coords_elem is not None:
                            return {
                                'type': geom_type,
                                'element': geom_elem,
                                'coordinates': coords_elem.text if coords_elem.text else ''
                            }
                except Exception:
                    continue
        
        return None
    
    def _find_coordinates_element(self, geometry_elem: ET.Element, geom_type: str) -> Optional[ET.Element]:
        """Find coordinates element within geometry"""
        coord_patterns = [
            './/{http://www.opengis.net/kml/2.2}coordinates',
            './/coordinates',
            './/kml:coordinates'
        ]
        
        for pattern in coord_patterns:
            try:
                coords_elem = geometry_elem.find(pattern)
                if coords_elem is not None:
                    return coords_elem
            except Exception:
                continue
        
        return None
    
    def _analyze_coordinates(self, coord_text: str) -> Dict[str, Any]:
        """Analyze coordinate string for issues"""
        analysis = {
            'coordinates_found': 0,
            'coordinates_valid': 0,
            'raw_coordinates': [],
            'parsed_coordinates': [],
            'errors': [],
            'warnings': [],
            'coordinate_issues': []
        }
        
        if not coord_text or not coord_text.strip():
            analysis['errors'].append("Coordinate string is empty")
            return analysis
        
        # Split coordinate string
        coord_pairs = coord_text.strip().split()
        analysis['coordinates_found'] = len(coord_pairs)
        
        if analysis['coordinates_found'] == 0:
            analysis['errors'].append("No coordinate pairs found in coordinate string")
            return analysis
        
        # Analyze each coordinate pair
        for i, coord_pair in enumerate(coord_pairs):
            analysis['raw_coordinates'].append(coord_pair)
            
            # Validate coordinate format
            match = self.coordinate_pattern.match(coord_pair)
            if match:
                lon, lat, alt = match.groups()
                analysis['coordinates_valid'] += 1
                
                # Check coordinate ranges
                try:
                    lon_val, lat_val = float(lon), float(lat)
                    if not (-180 <= lon_val <= 180):
                        analysis['warnings'].append(f"Coordinate {i+1}: Longitude {lon_val} is outside valid range (-180 to 180)")
                    if not (-90 <= lat_val <= 90):
                        analysis['warnings'].append(f"Coordinate {i+1}: Latitude {lat_val} is outside valid range (-90 to 90)")
                    
                    analysis['parsed_coordinates'].append([lon_val, lat_val, float(alt) if alt else 0])
                    
                except ValueError:
                    analysis['coordinate_issues'].append(f"Coordinate {i+1}: Non-numeric values in '{coord_pair}'")
            else:
                analysis['coordinate_issues'].append(f"Coordinate {i+1}: Invalid format '{coord_pair}' (expected: lon,lat[,alt])")
        
        # Generate suggestions for coordinate issues
        if analysis['coordinate_issues']:
            analysis['suggestions'].append("Fix coordinate format - use 'lon,lat,alt' format with numeric values")
        
        return analysis
    
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
    
    def _generate_suggestions(self, result: Dict[str, Any]) -> None:
        """Generate helpful suggestions based on analysis"""
        if result['features_found'] == 0:
            result['suggestions'].append("Add <Placemark> elements to your KML file")
        
        if result['geometries_found'] == 0 and result['features_found'] > 0:
            result['suggestions'].append("Add geometry elements (Point, LineString, Polygon) to your Placemarks")
        
        if result['coordinates_found'] == 0 and result['geometries_found'] > 0:
            result['suggestions'].append("Add <coordinates> elements to your geometry elements")
        
        if result['coordinates_found'] > 0 and result['coordinates_found'] != result['coordinates_valid']:
            result['suggestions'].append("Fix coordinate format issues - ensure all coordinates are in 'lon,lat,alt' format")
        
        # Check for common issues
        structure = result.get('structure_analysis', {})
        if structure.get('geometry_types'):
            unsupported = structure['geometry_types'] - set(self.supported_geometries)
            if unsupported:
                result['warnings'].append(f"Unsupported geometry types found: {', '.join(unsupported)}")
    
    def auto_fix_coordinates(self, coord_text: str) -> Tuple[str, List[str]]:
        """
        Attempt to fix common coordinate issues
        
        Returns:
            Tuple of (fixed_coordinates, list_of_fixes_applied)
        """
        fixes = []
        fixed_text = coord_text
        
        if not fixed_text:
            return fixed_text, fixes
        
        # Fix 1: Trim whitespace
        if fixed_text != fixed_text.strip():
            fixed_text = fixed_text.strip()
            fixes.append("Trimmed whitespace")
        
        # Fix 2: Handle missing altitude
        coord_pairs = fixed_text.split()
        fixed_pairs = []
        
        for pair in coord_pairs:
            parts = pair.split(',')
            if len(parts) == 2:
                # Add altitude if missing
                fixed_pairs.append(f"{parts[0]},{parts[1]},0")
                fixes.append("Added missing altitude values")
            elif len(parts) == 3:
                fixed_pairs.append(pair)
            else:
                # Skip invalid pairs
                continue
        
        fixed_text = ' '.join(fixed_pairs)
        
        # Fix 3: Handle lat,lon vs lon,lat (basic detection)
        # This is a simplified fix - in practice you'd need more sophisticated detection
        if fixed_pairs:
            first_pair = fixed_pairs[0]
            parts = first_pair.split(',')
            if len(parts) >= 2:
                try:
                    val1, val2 = float(parts[0]), float(parts[1])
                    # If first value looks like latitude (0-90) and second like longitude (-180 to 180)
                    if 0 <= abs(val1) <= 90 and abs(val2) > 90:
                        # Swap lat,lon to lon,lat
                        fixed_pairs = []
                        for pair in coord_pairs:
                            parts = pair.split(',')
                            if len(parts) >= 2:
                                fixed_pairs.append(f"{parts[1]},{parts[0]},{parts[2] if len(parts) > 2 else '0'}")
                        fixed_text = ' '.join(fixed_pairs)
                        fixes.append("Converted lat,lon format to lon,lat format")
                except ValueError:
                    pass
        
        return fixed_text, fixes

# Global validator instance
kml_validator = KMLValidator() 