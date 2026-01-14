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
