"""seismic_attributes.py
Seismic attribute computation for guided horizon tracking.
Similar to attributes used in Petrel for automatic interpretation.

PZero© Andrea Bistacchi
"""

import numpy as np
from scipy import ndimage, signal
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor


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

    def clear_cache(self):
        """Clear the attribute cache."""
        self._cache.clear()
