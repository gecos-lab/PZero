"""autotracker.py
Automatic horizon tracking using seismic attributes and dynamic programming.
Similar to Petrel's autotracking capabilities.

PZero© Andrea Bistacchi
"""

import numpy as np
from scipy.ndimage import gaussian_filter1d, median_filter
from typing import Dict, List, Tuple, Optional, Callable, Set
from enum import Flag, auto

from .seismic_attributes import SeismicAttributes


class TrackingAttribute(Flag):
    """
    Tracking attributes that can be combined using bitwise OR.
    Example: TrackingAttribute.AMPLITUDE | TrackingAttribute.EDGE
    """
    NONE = 0
    AMPLITUDE = auto()      # Track by amplitude (reflection strength)
    EDGE = auto()           # Track by edge strength (Sobel gradient)
    PHASE = auto()          # Track by phase continuity
    SIMILARITY = auto()     # Track by trace-to-trace similarity
    DIP = auto()            # Track by dip direction consistency
    
    @classmethod
    def from_strings(cls, attr_list: List[str]) -> 'TrackingAttribute':
        """Convert list of attribute names to combined flag."""
        result = cls.NONE
        mapping = {
            'amplitude': cls.AMPLITUDE,
            'edge': cls.EDGE,
            'phase': cls.PHASE,
            'similarity': cls.SIMILARITY,
            'dip': cls.DIP,
        }
        for attr in attr_list:
            if attr.lower() in mapping:
                result |= mapping[attr.lower()]
        return result
    
    def to_list(self) -> List[str]:
        """Convert flag to list of attribute names."""
        result = []
        if self & TrackingAttribute.AMPLITUDE:
            result.append('amplitude')
        if self & TrackingAttribute.EDGE:
            result.append('edge')
        if self & TrackingAttribute.PHASE:
            result.append('phase')
        if self & TrackingAttribute.SIMILARITY:
            result.append('similarity')
        if self & TrackingAttribute.DIP:
            result.append('dip')
        return result


class Autotracker:
    """
    Automatic horizon tracking system using seismic attributes and dynamic programming.

    Features:
    - Seismic attribute-guided tracking
    - Combinable tracking attributes (amplitude, edge, phase, similarity, dip)
    - Dynamic programming for optimal paths
    - Quality metrics and confidence scores
    """

    def __init__(self, attributes_processor: SeismicAttributes = None):
        """
        Initialize the autotracker.

        Args:
            attributes_processor: SeismicAttributes instance
        """
        self.attributes_processor = attributes_processor or SeismicAttributes()

        # Default tracking parameters
        self.tracking_params = {
            'search_window': 15,        # Search window size (samples)
            'smooth_sigma': 2.0,        # Gaussian smoothing sigma
            'max_jump': 3,              # Maximum jump between slices (samples)
            'smoothness_weight': 0.3,   # Weight for path smoothness (0-1)
            'amplitude_weight': 0.3,    # Weight for amplitude
            'edge_weight': 0.2,         # Weight for edge strength
            'phase_weight': 0.2,        # Weight for phase
            'similarity_weight': 0.15,  # Weight for similarity
            'dip_weight': 0.15,         # Weight for dip direction
        }

        # Store previous dip for consistency tracking
        self._prev_dip = None

    def set_tracking_parameters(self, **params):
        """Update tracking parameters."""
        self.tracking_params.update(params)

    def track_horizon(
        self,
        data_3d: np.ndarray,
        seed_positions: List[Tuple[int, int]],
        seed_slice_idx: int,
        axis: str,
        slices_to_track: List[int],
        attributes: TrackingAttribute = TrackingAttribute.AMPLITUDE | TrackingAttribute.EDGE,
        search_window: int = 15,
        smooth_sigma: float = 2.0,
        max_jump: int = 3,
        smoothness_weight: float = 0.3,
        amplitude_weight: float = 0.3,
        edge_weight: float = 0.2,
        phase_weight: float = 0.2,
        similarity_weight: float = 0.15,
        dip_weight: float = 0.15,
        progress_callback: Optional[Callable] = None
    ) -> Tuple[bool, Dict[int, List[Tuple[int, int]]], str]:
        """
        Track horizon through slices using attribute-guided dynamic programming.

        Args:
            data_3d: 3D seismic data array
            seed_positions: List of (row, col) seed points on the starting slice
            seed_slice_idx: Starting slice index
            axis: 'Inline', 'Crossline', or 'Z-slice'
            slices_to_track: List of slice indices to propagate to
            attributes: Combined tracking attributes (use | to combine)
            search_window: Vertical search range on each new slice (samples)
            smooth_sigma: Gaussian smoothing sigma for horizon smoothing
            max_jump: Maximum allowed jump between adjacent slices (samples)
            smoothness_weight: Weight for preferring smooth paths (0-1)
            amplitude_weight: Weight for amplitude tracking
            edge_weight: Weight for edge strength tracking
            phase_weight: Weight for phase continuity tracking
            similarity_weight: Weight for similarity tracking
            dip_weight: Weight for dip direction tracking
            progress_callback: Optional callback(msg, pct) for progress updates

        Returns:
            (success, horizons_dict, message)
            - horizons_dict: {slice_idx: [(row, col), ...]} for each tracked slice
        """
        # Update parameters
        self.tracking_params.update({
            'search_window': search_window,
            'smooth_sigma': smooth_sigma,
            'max_jump': max_jump,
            'smoothness_weight': smoothness_weight,
            'amplitude_weight': amplitude_weight,
            'edge_weight': edge_weight,
            'phase_weight': phase_weight,
            'similarity_weight': similarity_weight,
            'dip_weight': dip_weight,
        })

        def update_progress(msg, pct=None):
            if progress_callback:
                progress_callback(msg, pct)

        attr_names = attributes.to_list() if attributes != TrackingAttribute.NONE else ['amplitude']
        update_progress(f"Starting tracking with: {', '.join(attr_names)}...", 0)

        horizons = {}
        horizons[seed_slice_idx] = list(seed_positions)

        current_positions = list(seed_positions)
        total_slices = len(slices_to_track)

        if total_slices == 0:
            return True, horizons, "No slices to track"

        # Reset dip tracking
        self._prev_dip = None

        try:
            for i, slice_idx in enumerate(slices_to_track):
                # Extract slice data based on axis
                if axis == 'Inline':
                    slice_data = data_3d[slice_idx, :, :]
                elif axis == 'Crossline':
                    slice_data = data_3d[:, slice_idx, :]
                else:  # Z-slice
                    slice_data = data_3d[:, :, slice_idx]

                # Track horizon on this slice
                new_positions = self._track_on_slice(
                    slice_data, current_positions, attributes
                )

                # Apply smoothing
                new_positions = self._smooth_positions(new_positions)

                horizons[slice_idx] = new_positions
                current_positions = new_positions

                # Progress update every 10 slices
                if (i + 1) % 10 == 0 or i == total_slices - 1:
                    pct = int(100 * (i + 1) / total_slices)
                    update_progress(f"Processed slice {slice_idx} ({i+1}/{total_slices})", pct)

            update_progress(f"Tracking complete: {len(horizons)} slices", 100)
            return True, horizons, f"Tracked {len(horizons)} slices"

        except Exception as e:
            import traceback
            return False, horizons, f"Tracking error: {str(e)}\n{traceback.format_exc()}"

    def _track_on_slice(
        self,
        slice_data: np.ndarray,
        seed_positions: List[Tuple[int, int]],
        attributes: TrackingAttribute
    ) -> List[Tuple[int, int]]:
        """
        Track horizon points on a single slice using attribute-guided search.

        Args:
            slice_data: 2D seismic slice
            seed_positions: List of (row, col) positions from previous slice
            attributes: Combined tracking attributes

        Returns:
            List of updated (row, col) positions
        """
        h, w = slice_data.shape
        search_window = self.tracking_params['search_window']

        # Determine which attributes to compute based on selected flags
        attr_types = []
        if attributes & TrackingAttribute.AMPLITUDE:
            attr_types.append('amplitude')
        if attributes & TrackingAttribute.EDGE:
            attr_types.append('edge_strength')
        if attributes & TrackingAttribute.PHASE:
            attr_types.append('phase')
        if attributes & TrackingAttribute.SIMILARITY:
            attr_types.append('similarity')
        if attributes & TrackingAttribute.DIP:
            attr_types.extend(['dip_azimuth', 'dip_magnitude'])

        # Ensure at least amplitude is computed
        if not attr_types:
            attr_types = ['amplitude']

        computed_attrs = self.attributes_processor.compute_slice_attributes(
            slice_data, attr_types
        )

        new_positions = []

        for row, expected_col in seed_positions:
            # Ensure indices are within bounds
            row = int(np.clip(row, 0, h - 1))
            expected_col = int(np.clip(expected_col, 0, w - 1))

            # Define search range (vertical search around expected column)
            col_min = max(0, expected_col - search_window)
            col_max = min(w, expected_col + search_window + 1)

            # Compute cost for each candidate position
            best_col = expected_col
            best_cost = float('inf')

            for candidate_col in range(col_min, col_max):
                cost = self._compute_tracking_cost(
                    computed_attrs, row, candidate_col, expected_col, attributes
                )

                if cost < best_cost:
                    best_cost = cost
                    best_col = candidate_col

            new_positions.append((row, best_col))

        # Update previous dip for next slice
        if attributes & TrackingAttribute.DIP and 'dip_azimuth' in computed_attrs:
            cols = [p[1] for p in new_positions]
            rows = [p[0] for p in new_positions]
            if cols:
                avg_dip = np.mean([computed_attrs['dip_azimuth'][r, c] 
                                   for r, c in zip(rows, cols) 
                                   if 0 <= r < h and 0 <= c < w])
                self._prev_dip = avg_dip

        return new_positions

    def _compute_tracking_cost(
        self,
        attributes: Dict[str, np.ndarray],
        row: int,
        col: int,
        expected_col: int,
        tracking_attrs: TrackingAttribute
    ) -> float:
        """
        Compute cost for a candidate position based on selected attributes.

        Lower cost = better match for horizon tracking.
        """
        cost = 0.0
        search_window = self.tracking_params['search_window']
        smoothness_weight = self.tracking_params['smoothness_weight']

        # Distance penalty (prefer staying close to expected position)
        distance = abs(col - expected_col)
        distance_cost = (distance / max(search_window, 1)) ** 2
        cost += distance_cost * smoothness_weight

        # Count active attributes for normalization
        active_count = bin(tracking_attrs.value).count('1') if tracking_attrs != TrackingAttribute.NONE else 1

        # Amplitude-based cost (higher amplitude = lower cost)
        if tracking_attrs & TrackingAttribute.AMPLITUDE:
            weight = self.tracking_params['amplitude_weight']
            if 'amplitude' in attributes:
                amp = attributes['amplitude']
                amp_val = amp[row, col]
                amp_max = amp[row, :].max()
                amp_min = amp[row, :].min()
                if amp_max > amp_min:
                    amp_cost = 1.0 - (amp_val - amp_min) / (amp_max - amp_min)
                    cost += amp_cost * weight

        # Edge-based cost (higher edge strength = lower cost)
        if tracking_attrs & TrackingAttribute.EDGE:
            weight = self.tracking_params['edge_weight']
            if 'edge_strength' in attributes:
                edge = attributes['edge_strength']
                edge_val = edge[row, col]
                edge_max = edge[row, :].max()
                edge_min = edge[row, :].min()
                if edge_max > edge_min:
                    edge_cost = 1.0 - (edge_val - edge_min) / (edge_max - edge_min)
                    cost += edge_cost * weight

        # Phase-based cost (phase continuity)
        if tracking_attrs & TrackingAttribute.PHASE:
            weight = self.tracking_params['phase_weight']
            if 'phase' in attributes:
                phase = attributes['phase']
                w = phase.shape[1]
                if 0 < col < w - 1:
                    # Prefer positions where phase gradient is high (horizon boundary)
                    phase_grad = abs(phase[row, col+1] - phase[row, col-1])
                    # Normalize by max gradient in row
                    phase_grads = np.abs(np.diff(phase[row, :]))
                    max_grad = phase_grads.max() if len(phase_grads) > 0 else 1.0
                    if max_grad > 0:
                        phase_cost = 1.0 - phase_grad / (2 * max_grad)
                        cost += phase_cost * weight

        # Similarity-based cost (higher similarity = lower cost)
        if tracking_attrs & TrackingAttribute.SIMILARITY:
            weight = self.tracking_params['similarity_weight']
            if 'similarity' in attributes:
                sim = attributes['similarity']
                sim_val = sim[row, col]
                sim_cost = 1.0 - (sim_val + 1) / 2  # Normalize [-1,1] to [0,1]
                cost += sim_cost * weight

        # Dip-based cost (prefer consistent dip direction)
        if tracking_attrs & TrackingAttribute.DIP:
            weight = self.tracking_params['dip_weight']
            if 'dip_azimuth' in attributes and 'dip_magnitude' in attributes:
                dip_az = attributes['dip_azimuth']
                dip_mag = attributes['dip_magnitude']
                
                current_dip = dip_az[row, col]
                current_mag = dip_mag[row, col]
                
                # Prefer positions with consistent dip direction from previous slice
                if self._prev_dip is not None:
                    # Angular difference (handle wrap-around)
                    dip_diff = abs(current_dip - self._prev_dip)
                    dip_diff = min(dip_diff, 2 * np.pi - dip_diff)
                    dip_cost = dip_diff / np.pi  # Normalize to [0,1]
                    cost += dip_cost * weight
                else:
                    # First slice: prefer low dip magnitude (more horizontal = more stable horizon)
                    mag_max = dip_mag[row, :].max()
                    if mag_max > 0:
                        mag_cost = current_mag / mag_max
                        cost += mag_cost * weight * 0.5

        return cost

    def _smooth_positions(self, positions: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Apply smoothing to horizon positions."""
        if len(positions) < 5:
            return positions

        rows = np.array([p[0] for p in positions])
        cols = np.array([p[1] for p in positions], dtype=np.float64)

        # Median filter to remove outliers
        cols_smoothed = median_filter(cols, size=5)

        # Gaussian smoothing
        sigma = self.tracking_params['smooth_sigma']
        if sigma > 0:
            cols_smoothed = gaussian_filter1d(cols_smoothed, sigma=sigma)

        # Limit max jump between adjacent points
        max_jump = self.tracking_params['max_jump']
        for j in range(1, len(cols_smoothed)):
            diff = cols_smoothed[j] - cols_smoothed[j-1]
            if abs(diff) > max_jump:
                cols_smoothed[j] = cols_smoothed[j-1] + np.sign(diff) * max_jump

        return [(int(rows[j]), int(round(cols_smoothed[j]))) for j in range(len(rows))]

    def compute_tracking_quality(self, horizons: Dict[int, List[Tuple[int, int]]]) -> Dict[str, float]:
        """Compute quality metrics for tracking results."""
        metrics = {
            'path_smoothness': 0.0,
            'coverage': 0.0,
            'overall_quality': 0.0
        }

        if not horizons:
            return metrics

        smoothness_scores = []
        for slice_idx, positions in horizons.items():
            if len(positions) > 2:
                cols = np.array([p[1] for p in positions])
                d1 = np.diff(cols)
                d2 = np.diff(d1)
                curvature = np.mean(np.abs(d2))
                smoothness_scores.append(1.0 / (1.0 + curvature))

        if smoothness_scores:
            metrics['path_smoothness'] = np.mean(smoothness_scores)

        metrics['coverage'] = len(horizons)
        metrics['overall_quality'] = metrics['path_smoothness']

        return metrics


def propagate_horizon(
    data_3d: np.ndarray,
    seed_positions: List[Tuple[int, int]],
    seed_slice_idx: int,
    axis: str,
    slices_to_track: List[int],
    attributes: List[str] = None,
    search_window: int = 15,
    smooth_sigma: float = 2.0,
    max_jump: int = 3,
    smoothness_weight: float = 0.3,
    amplitude_weight: float = 0.3,
    edge_weight: float = 0.2,
    phase_weight: float = 0.2,
    similarity_weight: float = 0.15,
    dip_weight: float = 0.15,
    progress_callback: Optional[Callable] = None
) -> Tuple[bool, Dict[int, List[Tuple[int, int]]], str]:
    """
    Main function to propagate horizon using attribute-guided tracking.

    Args:
        data_3d: 3D seismic data array
        seed_positions: List of (row, col) seed points on the starting slice
        seed_slice_idx: Starting slice index
        axis: 'Inline', 'Crossline', or 'Z-slice'
        slices_to_track: List of slice indices to propagate to
        attributes: List of attributes to use for tracking. Options:
                   ['amplitude', 'edge', 'phase', 'similarity', 'dip']
                   Can combine multiple (e.g., ['amplitude', 'edge', 'dip'])
        search_window: Vertical search range on each new slice (samples)
        smooth_sigma: Gaussian smoothing sigma for horizon smoothing
        max_jump: Maximum allowed jump between adjacent slices (samples)
        smoothness_weight: Weight for preferring smooth paths (0-1)
        amplitude_weight: Weight for amplitude tracking
        edge_weight: Weight for edge strength tracking  
        phase_weight: Weight for phase continuity tracking
        similarity_weight: Weight for similarity tracking
        dip_weight: Weight for dip direction tracking
        progress_callback: Optional callback(msg, pct) for progress updates

    Returns:
        (success, horizons_dict, message)
    """
    # Default to amplitude + edge if nothing specified
    if attributes is None or len(attributes) == 0:
        attributes = ['amplitude', 'edge']

    # Convert string list to flag
    tracking_attrs = TrackingAttribute.from_strings(attributes)

    # Create autotracker and run
    autotracker = Autotracker()

    return autotracker.track_horizon(
        data_3d=data_3d,
        seed_positions=seed_positions,
        seed_slice_idx=seed_slice_idx,
        axis=axis,
        slices_to_track=slices_to_track,
        attributes=tracking_attrs,
        search_window=search_window,
        smooth_sigma=smooth_sigma,
        max_jump=max_jump,
        smoothness_weight=smoothness_weight,
        amplitude_weight=amplitude_weight,
        edge_weight=edge_weight,
        phase_weight=phase_weight,
        similarity_weight=similarity_weight,
        dip_weight=dip_weight,
        progress_callback=progress_callback
    )


# ==================== FAULT TRACKING ====================

class FaultAttribute(Flag):
    """Fault tracking attributes that can be combined."""
    NONE = 0
    VERTICAL_EDGE = auto()    # Vertical edge strength (most important)
    DISCONTINUITY = auto()    # Reflector discontinuity
    VARIANCE = auto()         # Local variance
    LIKELIHOOD = auto()       # Combined fault likelihood
    
    @classmethod
    def from_strings(cls, attr_list: List[str]) -> 'FaultAttribute':
        """Convert list of attribute names to combined flag."""
        result = cls.NONE
        mapping = {
            'vertical_edge': cls.VERTICAL_EDGE,
            'edge': cls.VERTICAL_EDGE,
            'discontinuity': cls.DISCONTINUITY,
            'variance': cls.VARIANCE,
            'likelihood': cls.LIKELIHOOD,
        }
        for attr in attr_list:
            if attr.lower() in mapping:
                result |= mapping[attr.lower()]
        return result
    
    def to_list(self) -> List[str]:
        """Convert flag to list of attribute names."""
        result = []
        if self & FaultAttribute.VERTICAL_EDGE:
            result.append('vertical_edge')
        if self & FaultAttribute.DISCONTINUITY:
            result.append('discontinuity')
        if self & FaultAttribute.VARIANCE:
            result.append('variance')
        if self & FaultAttribute.LIKELIHOOD:
            result.append('likelihood')
        return result


class FaultTracker:
    """
    Automatic fault tracking system using fault-specific attributes.

    Unlike horizons (horizontal), faults are near-vertical features.
    We track vertically down each slice, then propagate across slices.
    Faults shift horizontally as we move through slices (unlike horizons which follow reflectors).
    """

    def __init__(self, attributes_processor: SeismicAttributes = None):
        """Initialize the fault tracker."""
        self.attributes_processor = attributes_processor or SeismicAttributes()

        # Default fault tracking parameters - more aggressive than horizons
        # Faults can shift significantly between slices
        self.tracking_params = {
            'search_window': 20,         # Wider search - faults shift more than horizons
            'smooth_sigma': 0.8,         # Less smoothing - allow more variation
            'max_jump': 5,               # Allow bigger jumps for faults
            'vertical_edge_weight': 0.6, # Strong weight for vertical edges (key fault feature)
            'discontinuity_weight': 0.4, # Discontinuity indicates fault
            'variance_weight': 0.2,      # Variance can help
            'smoothness_weight': 0.1,    # LOW smoothness - let attributes guide more
            # New: smoothness of the fault trace *along depth* (prevents zig-zag jitter)
            'depth_smoothness_weight': 0.6,
            # New: how strongly we stay close to previous slice position (per depth sample)
            'prior_weight': 0.4,
        }

    def set_tracking_parameters(self, **params):
        """Update tracking parameters."""
        self.tracking_params.update(params)

    def track_fault(
        self,
        data_3d: np.ndarray,
        seed_points: List[Tuple[int, int]],
        seed_slice_idx: int,
        axis: str,
        slices_to_track: List[int],
        attributes: FaultAttribute = FaultAttribute.VERTICAL_EDGE | FaultAttribute.DISCONTINUITY,
        search_window: int = 20,
        smooth_sigma: float = 0.8,
        max_jump: int = 5,
        vertical_edge_weight: float = 0.6,
        discontinuity_weight: float = 0.4,
        variance_weight: float = 0.2,
        smoothness_weight: float = 0.1,
        progress_callback: Optional[Callable] = None
    ) -> Tuple[bool, Dict[int, List[Tuple[int, int]]], str]:
        """
        Track fault through slices.
        
        Faults are tracked vertically on each slice (down the rows),
        then the fault position is propagated to adjacent slices.
        
        Args:
            data_3d: 3D seismic data array
            seed_points: List of (row, col) seed points on the fault
            seed_slice_idx: Starting slice index
            axis: 'Inline', 'Crossline', or 'Z-slice'
            slices_to_track: List of slice indices to propagate to
            attributes: Combined fault attributes to use
            search_window: Horizontal search range (samples)
            smooth_sigma: Gaussian smoothing sigma
            max_jump: Maximum horizontal jump between rows
            vertical_edge_weight: Weight for vertical edge attribute
            discontinuity_weight: Weight for discontinuity attribute
            variance_weight: Weight for variance attribute
            smoothness_weight: Weight for smooth fault traces
            progress_callback: Optional callback(msg, pct) for progress

        Returns:
            (success, faults_dict, message)
            - faults_dict: {slice_idx: [(row, col), ...]} fault trace per slice
        """
        self.tracking_params.update({
            'search_window': search_window,
            'smooth_sigma': smooth_sigma,
            'max_jump': max_jump,
            'vertical_edge_weight': vertical_edge_weight,
            'discontinuity_weight': discontinuity_weight,
            'variance_weight': variance_weight,
            'smoothness_weight': smoothness_weight,
        })

        def update_progress(msg, pct=None):
            if progress_callback:
                progress_callback(msg, pct)

        attr_names = attributes.to_list() if attributes != FaultAttribute.NONE else ['vertical_edge']
        update_progress(f"Starting fault tracking with: {', '.join(attr_names)}...", 0)

        faults = {}
        
        # IMPORTANT: The seed_points from the user's drawn line ARE the fault trace
        # We do NOT extend vertically - the user has already defined where the fault is
        # We just propagate this trace horizontally to adjacent slices
        
        # Sort seed points by row (vertical position) and use them directly
        seed_fault = sorted(seed_points, key=lambda p: p[0])
        faults[seed_slice_idx] = seed_fault
        
        current_fault = seed_fault
        total_slices = len(slices_to_track)
        
        if total_slices == 0:
            return True, faults, "No slices to track"

        try:
            for i, slice_idx in enumerate(slices_to_track):
                # Extract slice data
                if axis == 'Inline':
                    slice_data = data_3d[slice_idx, :, :]
                elif axis == 'Crossline':
                    slice_data = data_3d[:, slice_idx, :]
                else:
                    slice_data = data_3d[:, :, slice_idx]

                # Track fault on this slice using previous fault as guide
                new_fault = self._propagate_fault_to_slice(
                    slice_data, current_fault, attributes
                )
                
                # Smooth the fault trace
                new_fault = self._smooth_fault_trace(new_fault)
                
                faults[slice_idx] = new_fault
                current_fault = new_fault

                if (i + 1) % 10 == 0 or i == total_slices - 1:
                    pct = int(100 * (i + 1) / total_slices)
                    update_progress(f"Processed slice {slice_idx} ({i+1}/{total_slices})", pct)

            update_progress(f"Fault tracking complete: {len(faults)} slices", 100)
            return True, faults, f"Tracked fault on {len(faults)} slices"

        except Exception as e:
            import traceback
            return False, faults, f"Fault tracking error: {str(e)}\n{traceback.format_exc()}"

    def _track_fault_on_slice(
        self,
        slice_data: np.ndarray,
        seed_points: List[Tuple[int, int]],
        attributes: FaultAttribute
    ) -> List[Tuple[int, int]]:
        """
        Track fault vertically on a single slice starting from seed points.
        Extends the fault trace both up and down from the seeds.
        """
        h, w = slice_data.shape
        
        # Compute fault attributes
        fault_attrs = self.attributes_processor.compute_fault_attributes(slice_data)
        
        # Sort seed points by row
        seed_points = sorted(seed_points, key=lambda p: p[0])
        
        # Get initial column positions from seeds
        if len(seed_points) == 1:
            seed_row, seed_col = seed_points[0]
        else:
            # Use average column from multiple seeds
            seed_col = int(np.mean([p[1] for p in seed_points]))
            seed_row = seed_points[len(seed_points)//2][0]
        
        # Track upward from seed
        upper_trace = self._track_fault_direction(
            fault_attrs, seed_row, seed_col, -1, h, w, attributes
        )
        
        # Track downward from seed
        lower_trace = self._track_fault_direction(
            fault_attrs, seed_row, seed_col, 1, h, w, attributes
        )
        
        # Combine traces (upper reversed + seed + lower)
        full_trace = upper_trace[::-1] + [(seed_row, seed_col)] + lower_trace
        
        return full_trace

    def _track_fault_direction(
        self,
        fault_attrs: Dict[str, np.ndarray],
        start_row: int,
        start_col: int,
        direction: int,
        h: int,
        w: int,
        attributes: FaultAttribute
    ) -> List[Tuple[int, int]]:
        """
        Track fault in one direction (up or down).
        
        Args:
            direction: -1 for up, +1 for down
        """
        trace = []
        current_col = start_col
        search_window = self.tracking_params['search_window']
        
        row = start_row + direction
        while 0 <= row < h:
            # Search for best column position
            col_min = max(0, current_col - search_window)
            col_max = min(w, current_col + search_window + 1)
            
            best_col = current_col
            best_cost = float('inf')
            
            for candidate_col in range(col_min, col_max):
                cost = self._compute_fault_cost(
                    fault_attrs, row, candidate_col, current_col, attributes
                )
                if cost < best_cost:
                    best_cost = cost
                    best_col = candidate_col
            
            trace.append((row, best_col))
            current_col = best_col
            row += direction
        
        return trace

    def _propagate_fault_to_slice(
        self,
        slice_data: np.ndarray,
        prev_fault: List[Tuple[int, int]],
        attributes: FaultAttribute
    ) -> List[Tuple[int, int]]:
        """
        Propagate fault from previous slice to current slice.
        
        For faults:
        - Each point has (row, col) where row=X position, col=Z/depth position
        - The fault is vertical (varying col/Z)
        - As we move through slices, the fault shifts horizontally (in row/X)
        
        So we keep the Z position (col) fixed and search in X (row) direction.
        """
        h, w = slice_data.shape
        fault_attrs = self.attributes_processor.compute_fault_attributes(slice_data)

        # DP-based propagation: solve the whole fault trace on this slice at once.
        # We model the fault as row = f(col) and enforce:
        # - good attribute response at (row, col)
        # - closeness to previous slice (a prior per col)
        # - smoothness along col (prevents zig-zag jitter)

        col_grid, expected_rows = self._build_expected_row_by_col(prev_fault, w=w)
        if col_grid.size == 0:
            return []

        norm_attrs = self._normalize_fault_attrs(fault_attrs)

        search_window = int(self.tracking_params['search_window'])
        max_jump = max(1, int(self.tracking_params['max_jump']))
        depth_smooth_w = float(self.tracking_params.get('depth_smoothness_weight', 0.6))
        prior_w = float(self.tracking_params.get('prior_weight', 0.4))

        # Limit between-depth step to keep shape coherent, but allow real dip changes.
        max_step = max(3, int(round(max_jump * 2)))

        back_ptrs: List[np.ndarray] = []
        prev_rows: Optional[np.ndarray] = None
        prev_costs: Optional[np.ndarray] = None

        for i, col in enumerate(col_grid.tolist()):
            expected = int(np.clip(int(round(expected_rows[i])), 0, h - 1))

            row_min = max(0, expected - search_window)
            row_max = min(h - 1, expected + search_window)
            cand_rows = np.arange(row_min, row_max + 1, dtype=np.int32)

            base_cost = self._fault_attribute_cost_vector(norm_attrs, cand_rows, col, attributes)
            prior_cost = prior_w * ((cand_rows - expected) / max(search_window, 1)) ** 2
            node_cost = base_cost + prior_cost

            if prev_rows is None:
                # First column: no transition cost
                prev_rows = cand_rows
                prev_costs = node_cost.astype(np.float64)
                back_ptrs.append(np.full(cand_rows.shape, -1, dtype=np.int32))
                continue

            # Transition: penalize rapid horizontal changes along depth (col direction).
            # Compute pairwise diffs: shape (n_curr, n_prev)
            diff = np.abs(cand_rows[:, None] - prev_rows[None, :]).astype(np.float64)
            # Hard constraint to prevent extreme zig-zags
            diff[diff > max_step] = np.inf
            trans_cost = depth_smooth_w * (diff / max_step) ** 2

            # DP: curr_cost[j] = node_cost[j] + min_k(prev_costs[k] + trans_cost[j,k])
            scores = trans_cost + prev_costs[None, :]
            best_prev_idx = np.argmin(scores, axis=1).astype(np.int32)
            best_prev_score = scores[np.arange(scores.shape[0]), best_prev_idx]

            curr_costs = node_cost + best_prev_score

            back_ptrs.append(best_prev_idx)
            prev_rows = cand_rows
            prev_costs = curr_costs

        assert prev_rows is not None and prev_costs is not None

        # Backtrack best path
        path_rows = np.zeros(col_grid.shape[0], dtype=np.int32)
        j = int(np.argmin(prev_costs))
        for i in range(col_grid.shape[0] - 1, -1, -1):
            # Reconstruct the candidate row for this col
            # We need the candidate row array for this step; rebuild it deterministically.
            col = int(col_grid[i])
            expected = int(np.clip(int(round(expected_rows[i])), 0, h - 1))
            row_min = max(0, expected - search_window)
            row_max = min(h - 1, expected + search_window)
            cand_rows = np.arange(row_min, row_max + 1, dtype=np.int32)

            path_rows[i] = int(cand_rows[j])
            j = int(back_ptrs[i][j])
            if j < 0:
                break

        new_fault = [(int(path_rows[i]), int(col_grid[i])) for i in range(col_grid.shape[0])]
        return new_fault

    @staticmethod
    def _build_expected_row_by_col(prev_fault: List[Tuple[int, int]], w: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Convert a previous fault polyline into an expected row for each depth sample (col).

        Returns:
            col_grid: int array of cols to track (contiguous)
            expected_rows: float array aligned with col_grid
        """
        cols = np.array([c for r, c in prev_fault if 0 <= c < w], dtype=np.int32)
        if cols.size == 0:
            return np.array([], dtype=np.int32), np.array([], dtype=np.float64)
        rows = np.array([r for r, c in prev_fault if 0 <= c < w], dtype=np.float64)

        order = np.argsort(cols)
        cols = cols[order]
        rows = rows[order]

        # If multiple points share the same col, aggregate by median row
        unique_cols = np.unique(cols)
        if unique_cols.size != cols.size:
            med_rows = []
            for c in unique_cols.tolist():
                med_rows.append(float(np.median(rows[cols == c])))
            cols_u = unique_cols.astype(np.int32)
            rows_u = np.array(med_rows, dtype=np.float64)
        else:
            cols_u = cols
            rows_u = rows

        col_min = int(cols_u.min())
        col_max = int(cols_u.max())
        if col_max < col_min:
            return np.array([], dtype=np.int32), np.array([], dtype=np.float64)

        col_grid = np.arange(col_min, col_max + 1, dtype=np.int32)
        expected_rows = np.interp(col_grid.astype(np.float64), cols_u.astype(np.float64), rows_u)
        return col_grid, expected_rows

    @staticmethod
    def _normalize_fault_attrs(fault_attrs: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """Normalize attribute maps to 0..1 for stable weighting."""
        norm = {}
        for k, arr in fault_attrs.items():
            a = arr.astype(np.float32, copy=False)
            mn = float(np.nanmin(a))
            mx = float(np.nanmax(a))
            if np.isfinite(mn) and np.isfinite(mx) and mx > mn:
                norm[k] = (a - mn) / (mx - mn)
            else:
                norm[k] = np.zeros_like(a, dtype=np.float32)
        return norm

    def _fault_attribute_cost_vector(
        self,
        norm_attrs: Dict[str, np.ndarray],
        cand_rows: np.ndarray,
        col: int,
        attributes: FaultAttribute
    ) -> np.ndarray:
        """
        Vectorized attribute cost for a fixed col and multiple candidate rows.
        Lower cost is better.
        """
        cost = np.zeros(cand_rows.shape[0], dtype=np.float64)

        if attributes & FaultAttribute.VERTICAL_EDGE and 'vertical_edge' in norm_attrs:
            w_edge = float(self.tracking_params['vertical_edge_weight'])
            val = norm_attrs['vertical_edge'][cand_rows, col].astype(np.float64)
            cost += w_edge * np.sqrt(np.clip(1.0 - val, 0.0, 1.0))

        if attributes & FaultAttribute.DISCONTINUITY and 'discontinuity' in norm_attrs:
            w_disc = float(self.tracking_params['discontinuity_weight'])
            val = norm_attrs['discontinuity'][cand_rows, col].astype(np.float64)
            cost += w_disc * np.sqrt(np.clip(1.0 - val, 0.0, 1.0))

        if attributes & FaultAttribute.VARIANCE and 'variance' in norm_attrs:
            w_var = float(self.tracking_params['variance_weight'])
            val = norm_attrs['variance'][cand_rows, col].astype(np.float64)
            cost += w_var * np.sqrt(np.clip(1.0 - val, 0.0, 1.0))

        if attributes & FaultAttribute.LIKELIHOOD and 'fault_likelihood' in norm_attrs:
            w_like = 0.4  # keep consistent with prior behavior
            val = norm_attrs['fault_likelihood'][cand_rows, col].astype(np.float64)
            cost += w_like * np.sqrt(np.clip(1.0 - val, 0.0, 1.0))

        return cost
    
    def _compute_fault_cost_global(
        self,
        fault_attrs: Dict[str, np.ndarray],
        attr_norms: Dict[str, Tuple[float, float]],
        row: int,
        col: int,
        expected_row: int,
        attributes: FaultAttribute
    ) -> float:
        """
        Compute cost using global normalization for stronger attribute detection.
        """
        cost = 0.0
        search_window = self.tracking_params['search_window']
        # Lower smoothness weight for faults - they shift more than horizons
        smoothness_weight = self.tracking_params['smoothness_weight'] * 0.3
        
        # Distance penalty (much weaker for faults to allow more movement)
        distance = abs(row - expected_row)
        distance_cost = (distance / max(search_window * 2, 1)) ** 2
        cost += distance_cost * smoothness_weight
        
        total_attr_weight = 0.0
        
        # Vertical edge (higher = better for faults)
        if attributes & FaultAttribute.VERTICAL_EDGE:
            weight = self.tracking_params['vertical_edge_weight']
            if 'vertical_edge' in fault_attrs and 'vertical_edge' in attr_norms:
                edge = fault_attrs['vertical_edge']
                edge_val = edge[row, col]
                edge_min, edge_max = attr_norms['vertical_edge']
                if edge_max > edge_min:
                    # High edge = low cost (inverted and scaled strongly)
                    normalized = (edge_val - edge_min) / (edge_max - edge_min)
                    edge_cost = (1.0 - normalized) ** 0.5  # Square root makes it more sensitive
                    cost += edge_cost * weight
                    total_attr_weight += weight
        
        # Discontinuity (higher = better for faults)
        if attributes & FaultAttribute.DISCONTINUITY:
            weight = self.tracking_params['discontinuity_weight']
            if 'discontinuity' in fault_attrs and 'discontinuity' in attr_norms:
                disc = fault_attrs['discontinuity']
                disc_val = disc[row, col]
                disc_min, disc_max = attr_norms['discontinuity']
                if disc_max > disc_min:
                    normalized = (disc_val - disc_min) / (disc_max - disc_min)
                    disc_cost = (1.0 - normalized) ** 0.5
                    cost += disc_cost * weight
                    total_attr_weight += weight
        
        # Variance
        if attributes & FaultAttribute.VARIANCE:
            weight = self.tracking_params['variance_weight']
            if 'variance' in fault_attrs and 'variance' in attr_norms:
                var = fault_attrs['variance']
                var_val = var[row, col]
                var_min, var_max = attr_norms['variance']
                if var_max > var_min:
                    normalized = (var_val - var_min) / (var_max - var_min)
                    var_cost = (1.0 - normalized) ** 0.5
                    cost += var_cost * weight
                    total_attr_weight += weight
        
        # Fault likelihood
        if attributes & FaultAttribute.LIKELIHOOD:
            if 'fault_likelihood' in fault_attrs and 'fault_likelihood' in attr_norms:
                likelihood = fault_attrs['fault_likelihood']
                like_val = likelihood[row, col]
                like_min, like_max = attr_norms['fault_likelihood']
                if like_max > like_min:
                    normalized = (like_val - like_min) / (like_max - like_min)
                    like_cost = (1.0 - normalized) ** 0.5
                    cost += like_cost * 0.4
                    total_attr_weight += 0.4
        
        return cost

    def _compute_fault_cost(
        self,
        fault_attrs: Dict[str, np.ndarray],
        row: int,
        col: int,
        expected_row: int,
        attributes: FaultAttribute
    ) -> float:
        """
        Compute cost for a candidate fault position.
        Lower cost = better fault location.
        
        For fault propagation:
        - We search in the row (X/horizontal) direction
        - col (Z/depth) is kept fixed
        - We want to find the row that has the best fault attributes
        """
        cost = 0.0
        search_window = self.tracking_params['search_window']
        smoothness_weight = self.tracking_params['smoothness_weight']
        
        # Distance penalty (prefer staying close to expected row position)
        distance = abs(row - expected_row)
        distance_cost = (distance / max(search_window, 1)) ** 2
        cost += distance_cost * smoothness_weight
        
        # Vertical edge (higher = better for faults, so lower cost)
        # Normalize along the column since we're searching in row direction
        if attributes & FaultAttribute.VERTICAL_EDGE:
            weight = self.tracking_params['vertical_edge_weight']
            if 'vertical_edge' in fault_attrs:
                edge = fault_attrs['vertical_edge']
                edge_val = edge[row, col]
                # Normalize along the column (all rows at this col)
                edge_max = edge[:, col].max()
                edge_min = edge[:, col].min()
                if edge_max > edge_min:
                    # High edge = low cost
                    edge_cost = 1.0 - (edge_val - edge_min) / (edge_max - edge_min)
                    cost += edge_cost * weight
        
        # Discontinuity (higher = better for faults)
        if attributes & FaultAttribute.DISCONTINUITY:
            weight = self.tracking_params['discontinuity_weight']
            if 'discontinuity' in fault_attrs:
                disc = fault_attrs['discontinuity']
                disc_val = disc[row, col]
                # Normalize along the column
                disc_max = disc[:, col].max()
                disc_min = disc[:, col].min()
                if disc_max > disc_min:
                    disc_cost = 1.0 - (disc_val - disc_min) / (disc_max - disc_min)
                    cost += disc_cost * weight
        
        # Variance (higher = potentially fault zone)
        if attributes & FaultAttribute.VARIANCE:
            weight = self.tracking_params['variance_weight']
            if 'variance' in fault_attrs:
                var = fault_attrs['variance']
                var_val = var[row, col]
                # Normalize along the column
                var_max = var[:, col].max()
                var_min = var[:, col].min()
                if var_max > var_min:
                    var_cost = 1.0 - (var_val - var_min) / (var_max - var_min)
                    cost += var_cost * weight
        
        # Fault likelihood (combined attribute)
        if attributes & FaultAttribute.LIKELIHOOD:
            if 'fault_likelihood' in fault_attrs:
                likelihood = fault_attrs['fault_likelihood']
                like_val = likelihood[row, col]
                # Normalize along the column
                like_max = likelihood[:, col].max()
                like_min = likelihood[:, col].min()
                if like_max > like_min:
                    like_cost = 1.0 - (like_val - like_min) / (like_max - like_min)
                    cost += like_cost * 0.3
                else:
                    cost += (1.0 - like_val) * 0.3
        
        return cost

    def _smooth_fault_trace(self, fault: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """
        Apply light smoothing to fault trace to remove noise while preserving the fault's dip.
        
        For faults:
        - rows = X positions (these vary as the fault dips/shifts)
        - cols = Z positions (these stay fixed, defining the vertical extent)
        
        We smooth the row (X) values lightly to remove outliers without killing the trend.
        """
        if len(fault) < 3:
            return fault
        
        rows = np.array([p[0] for p in fault], dtype=np.float64)
        cols = np.array([p[1] for p in fault])
        
        # Only apply very light median filter to remove obvious outliers
        if len(rows) >= 5:
            rows_smoothed = median_filter(rows, size=3)
        else:
            rows_smoothed = rows.copy()
        
        # Very light Gaussian smoothing - faults should NOT be perfectly smooth
        sigma = self.tracking_params['smooth_sigma']
        if sigma > 0 and len(rows_smoothed) > 3:
            rows_smoothed = gaussian_filter1d(rows_smoothed, sigma=min(sigma, 1.0))
        
        # DO NOT apply max_jump constraint - faults can have variable dip
        # The attribute tracking should have already found reasonable positions
        
        return [(int(round(rows_smoothed[j])), int(cols[j])) for j in range(len(cols))]


def propagate_fault(
    data_3d: np.ndarray,
    seed_points: List[Tuple[int, int]],
    seed_slice_idx: int,
    axis: str,
    slices_to_track: List[int],
    attributes: List[str] = None,
    search_window: int = 20,
    smooth_sigma: float = 0.8,
    max_jump: int = 5,
    vertical_edge_weight: float = 0.6,
    discontinuity_weight: float = 0.4,
    variance_weight: float = 0.2,
    smoothness_weight: float = 0.1,
    progress_callback: Optional[Callable] = None
) -> Tuple[bool, Dict[int, List[Tuple[int, int]]], str]:
    """
    Main function to propagate fault using attribute-guided tracking.
    
    Args:
        data_3d: 3D seismic data array
        seed_points: List of (row, col) seed points on the fault
        seed_slice_idx: Starting slice index
        axis: 'Inline', 'Crossline', or 'Z-slice'
        slices_to_track: List of slice indices to propagate to
        attributes: List of attributes ['vertical_edge', 'discontinuity', 'variance', 'likelihood']
        search_window: Horizontal search range (samples)
        smooth_sigma: Gaussian smoothing sigma
        max_jump: Maximum horizontal jump between rows
        vertical_edge_weight: Weight for vertical edge
        discontinuity_weight: Weight for discontinuity
        variance_weight: Weight for variance
        smoothness_weight: Weight for smooth traces
        progress_callback: Optional callback(msg, pct)

    Returns:
        (success, faults_dict, message)
    """
    if attributes is None or len(attributes) == 0:
        attributes = ['vertical_edge', 'discontinuity']
    
    tracking_attrs = FaultAttribute.from_strings(attributes)
    
    tracker = FaultTracker()
    
    return tracker.track_fault(
        data_3d=data_3d,
        seed_points=seed_points,
        seed_slice_idx=seed_slice_idx,
        axis=axis,
        slices_to_track=slices_to_track,
        attributes=tracking_attrs,
        search_window=search_window,
        smooth_sigma=smooth_sigma,
        max_jump=max_jump,
        vertical_edge_weight=vertical_edge_weight,
        discontinuity_weight=discontinuity_weight,
        variance_weight=variance_weight,
        smoothness_weight=smoothness_weight,
        progress_callback=progress_callback
    )
