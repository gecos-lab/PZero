"""seismic_attributes.py
Seismic attribute computation for guided horizon and fault tracking.
Similar to attributes used in Petrel for automatic interpretation.

PZero© Andrea Bistacchi
"""

import numpy as np
from scipy import ndimage, signal
from typing import Dict, List, Tuple, Optional


class SeismicAttributes:
    """
    Computes seismic attributes for guided autotracking.
    Includes amplitude, phase, frequency, and structural attributes.
    """

    def __init__(self, use_gpu: bool = False):
        """
        Initialize seismic attributes processor.

        Args:
            use_gpu: Whether to use GPU acceleration (requires torch)
        """
        self.use_gpu = use_gpu
        self._cache = {}

        # Try to use GPU if requested
        if use_gpu:
            try:
                import torch
                self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                self._torch_available = torch.cuda.is_available()
            except ImportError:
                self._torch_available = False
                self.device = None
        else:
            self._torch_available = False
            self.device = None

    def compute_slice_attributes(self, slice_data: np.ndarray,
                                 attribute_types: List[str] = None) -> Dict[str, np.ndarray]:
        """
        Compute multiple seismic attributes for a single slice.

        Args:
            slice_data: 2D seismic slice
            attribute_types: List of attributes to compute. If None, computes all.

        Returns:
            Dictionary of computed attributes
        """
        if attribute_types is None:
            attribute_types = ['amplitude', 'phase', 'edge_strength', 'similarity']

        attributes = {}

        # Compute each attribute
        if 'amplitude' in attribute_types:
            attributes['amplitude'] = self.compute_amplitude(slice_data)

        if 'phase' in attribute_types:
            attributes['phase'] = self.compute_phase(slice_data)

        if 'frequency' in attribute_types:
            attributes['frequency'] = self.compute_instantaneous_frequency(slice_data)

        if 'similarity' in attribute_types:
            attributes['similarity'] = self.compute_similarity(slice_data)

        if 'edge_strength' in attribute_types:
            attributes['edge_strength'] = self.compute_edge_strength(slice_data)

        if 'dip_azimuth' in attribute_types or 'dip_magnitude' in attribute_types:
            dip_azimuth, dip_magnitude = self.compute_dip_attributes(slice_data)
            if 'dip_azimuth' in attribute_types:
                attributes['dip_azimuth'] = dip_azimuth
            if 'dip_magnitude' in attribute_types:
                attributes['dip_magnitude'] = dip_magnitude

        return attributes

    def compute_amplitude(self, data: np.ndarray) -> np.ndarray:
        """Compute amplitude attribute (envelope/reflection strength)."""
        # Apply Hilbert transform for envelope
        analytic_signal = signal.hilbert(data, axis=0)
        amplitude = np.abs(analytic_signal)
        return amplitude.astype(np.float32)

    def compute_phase(self, data: np.ndarray) -> np.ndarray:
        """Compute instantaneous phase."""
        analytic_signal = signal.hilbert(data, axis=0)
        phase = np.angle(analytic_signal)
        return phase.astype(np.float32)

    def compute_instantaneous_frequency(self, data: np.ndarray) -> np.ndarray:
        """Compute instantaneous frequency."""
        phase = self.compute_phase(data)

        # Compute frequency as derivative of phase
        freq = np.zeros_like(phase)

        # Central difference for interior points
        freq[1:-1] = (phase[2:] - phase[:-2]) / (2 * np.pi)

        # Forward/backward difference for boundaries
        freq[0] = (phase[1] - phase[0]) / np.pi
        freq[-1] = (phase[-1] - phase[-2]) / np.pi

        return freq.astype(np.float32)

    def compute_similarity(self, data: np.ndarray, window_size: int = 5) -> np.ndarray:
        """Compute trace-to-trace similarity (coherence-like attribute)."""
        h, w = data.shape
        similarity = np.zeros((h, w), dtype=np.float32)

        # Vectorized similarity computation
        for offset in range(1, min(window_size + 1, w)):
            if offset < w:
                trace1 = data[:, :-offset]
                trace2 = data[:, offset:]

                # Remove mean
                trace1_dm = trace1 - np.mean(trace1, axis=0, keepdims=True)
                trace2_dm = trace2 - np.mean(trace2, axis=0, keepdims=True)

                # Correlation coefficient
                numerator = np.sum(trace1_dm * trace2_dm, axis=0)
                denominator = np.sqrt(np.sum(trace1_dm**2, axis=0) * np.sum(trace2_dm**2, axis=0))

                mask = denominator > 1e-10
                corr = np.zeros(numerator.shape)
                corr[mask] = numerator[mask] / denominator[mask]

                # Add to similarity
                similarity[:, :-offset] += corr
                similarity[:, offset:] += corr

        # Average by number of neighbors
        count = np.zeros(w)
        for i in range(w):
            neighbors = min(i + window_size + 1, w) - max(0, i - window_size)
            count[i] = max(1, neighbors - 1)

        similarity = similarity / count[np.newaxis, :]
        return np.clip(similarity, -1, 1).astype(np.float32)

    def compute_dip_attributes(self, data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Compute dip azimuth and magnitude."""
        grad_y, grad_x = np.gradient(data.astype(np.float64))

        # Dip magnitude (steepness)
        dip_magnitude = np.sqrt(grad_x**2 + grad_y**2)

        # Dip azimuth (direction)
        dip_azimuth = np.arctan2(grad_y, grad_x)

        return dip_azimuth.astype(np.float32), dip_magnitude.astype(np.float32)

    def compute_edge_strength(self, data: np.ndarray) -> np.ndarray:
        """Compute edge strength using gradient magnitude."""
        sobel_x = ndimage.sobel(data.astype(np.float64), axis=1)
        sobel_y = ndimage.sobel(data.astype(np.float64), axis=0)

        edge_strength = np.sqrt(sobel_x**2 + sobel_y**2)
        return edge_strength.astype(np.float32)

    # ==================== FAULT-SPECIFIC ATTRIBUTES ====================

    def compute_fault_attributes(self, slice_data: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Compute all fault-specific attributes for a single slice.
        
        Returns dict with: vertical_edge, discontinuity, variance, fault_likelihood
        """
        return {
            'vertical_edge': self.compute_vertical_edge(slice_data),
            'discontinuity': self.compute_discontinuity(slice_data),
            'variance': self.compute_variance(slice_data),
            'fault_likelihood': self.compute_fault_likelihood(slice_data),
        }

    def compute_vertical_edge(self, data: np.ndarray) -> np.ndarray:
        """
        Compute vertical edge strength (horizontal gradient).
        Faults appear as vertical discontinuities, so we use horizontal Sobel.
        """
        # Horizontal Sobel detects vertical edges
        sobel_horizontal = ndimage.sobel(data.astype(np.float64), axis=1)
        vertical_edge = np.abs(sobel_horizontal)
        return vertical_edge.astype(np.float32)

    def compute_discontinuity(self, data: np.ndarray, window: int = 5) -> np.ndarray:
        """
        Compute discontinuity attribute (inverse of local coherence).
        High values indicate potential faults where reflectors are broken.
        """
        h, w = data.shape
        discontinuity = np.ones((h, w), dtype=np.float32)
        
        half_w = window // 2
        
        # Compare left and right windows for each position
        for col in range(half_w, w - half_w):
            left_window = data[:, col - half_w:col]
            right_window = data[:, col + 1:col + half_w + 1]
            
            # Compute correlation between left and right
            left_dm = left_window - np.mean(left_window, axis=1, keepdims=True)
            right_dm = right_window - np.mean(right_window, axis=1, keepdims=True)
            
            # Cross-correlation per row
            numerator = np.sum(left_dm * right_dm, axis=1)
            denom = np.sqrt(np.sum(left_dm**2, axis=1) * np.sum(right_dm**2, axis=1))
            
            mask = denom > 1e-10
            corr = np.zeros(h)
            corr[mask] = numerator[mask] / denom[mask]
            
            # Discontinuity is 1 - coherence (high where correlation is low)
            discontinuity[:, col] = 1.0 - np.clip(corr, 0, 1)
        
        return discontinuity

    def compute_variance(self, data: np.ndarray, window: int = 5) -> np.ndarray:
        """
        Compute local variance attribute.
        High variance often indicates fault zones.
        """
        # Use uniform filter for local mean
        local_mean = ndimage.uniform_filter(data.astype(np.float64), size=window)
        local_sqr_mean = ndimage.uniform_filter(data.astype(np.float64)**2, size=window)
        
        # Variance = E[X^2] - E[X]^2
        variance = local_sqr_mean - local_mean**2
        variance = np.maximum(variance, 0)  # Ensure non-negative
        
        return variance.astype(np.float32)

    def compute_fault_likelihood(self, data: np.ndarray) -> np.ndarray:
        """
        Compute combined fault likelihood attribute.
        Combines vertical edge, discontinuity, and variance into a single metric.
        """
        # Get individual attributes
        vert_edge = self.compute_vertical_edge(data)
        discont = self.compute_discontinuity(data)
        variance = self.compute_variance(data)
        
        # Normalize each to 0-1 range
        def normalize(arr):
            min_val, max_val = arr.min(), arr.max()
            if max_val > min_val:
                return (arr - min_val) / (max_val - min_val)
            return np.zeros_like(arr)
        
        vert_edge_norm = normalize(vert_edge)
        discont_norm = normalize(discont)
        variance_norm = normalize(variance)
        
        # Combine with weights (vertical edge most important for faults)
        fault_likelihood = (
            0.5 * vert_edge_norm +
            0.3 * discont_norm +
            0.2 * variance_norm
        )
        
        return fault_likelihood.astype(np.float32)

    def compute_fault_enhancement(self, data: np.ndarray, 
                                   enhancement_type: str = 'likelihood') -> np.ndarray:
        """
        Compute fault-enhanced display for visualization.
        
        Args:
            data: 2D seismic slice
            enhancement_type: 'likelihood', 'edge', 'discontinuity', 'variance', 'combined'
        
        Returns:
            Enhanced image highlighting fault locations
        """
        if enhancement_type == 'edge':
            enhanced = self.compute_vertical_edge(data)
        elif enhancement_type == 'discontinuity':
            enhanced = self.compute_discontinuity(data)
        elif enhancement_type == 'variance':
            enhanced = self.compute_variance(data)
        elif enhancement_type == 'likelihood':
            enhanced = self.compute_fault_likelihood(data)
        elif enhancement_type == 'combined':
            # Overlay fault likelihood on original data
            likelihood = self.compute_fault_likelihood(data)
            # Normalize original data
            data_norm = (data - data.min()) / (data.max() - data.min() + 1e-10)
            # Blend: show original where no fault, highlight where fault likely
            enhanced = data_norm * (1 - likelihood * 0.7) + likelihood * 0.7
        else:
            enhanced = self.compute_fault_likelihood(data)
        
        return enhanced.astype(np.float32)

    def clear_cache(self):
        """Clear the attribute cache."""
        self._cache.clear()
