"""gif_export_dialog.py
PZero© Andrea Bistacchi

High-quality GIF animation export dialog with camera orbit controls,
animation settings, and quality options for showcasing 3D geomodelling structures.
"""

import numpy as np
import tempfile
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QPushButton,
    QFormLayout,
    QLineEdit,
    QFileDialog,
    QMessageBox,
    QProgressDialog,
    QSlider,
)

import pyvista as pv

from ..properties_manager import PropertiesCMaps


class GifExportDialog(QDialog):
    """Dialog for exporting animated GIF files from PZero 3D views.
    
    This dialog provides comprehensive options for creating publication-quality
    animated GIFs including camera orbit controls, animation presets,
    visual settings, and quality options.
    
    Args:
        parent: The parent view window (ViewVTK subclass)
        plotter: The PyVista plotter to capture
        view_name: Name of the view for default filename (e.g., "3D", "Map", "XSection")
    """

    # Resolution presets: (name, width, height)
    RESOLUTION_PRESETS = [
        ("Web (640×480)", 640, 480),
        ("HD Ready (1280×720)", 1280, 720),
        ("HD (1920×1080)", 1920, 1080),
        ("2K (2560×1440)", 2560, 1440),
        ("Custom", 0, 0),
    ]

    # Animation type presets
    ANIMATION_PRESETS = [
        ("Full Orbit (360°)", "orbit_360", 360),
        ("Half Orbit (180°)", "orbit_180", 180),
        ("Quarter Orbit (90°)", "orbit_90", 90),
        ("Oscillate (±45°)", "oscillate_45", 90),
        ("Oscillate (±90°)", "oscillate_90", 180),
        ("Vertical Tilt (30°)", "tilt_30", 30),
        ("Zoom In/Out", "zoom", 0),
        ("Turntable (360°)", "turntable", 360),
        ("Custom Orbit", "custom", 0),
    ]

    # Orbit axis options
    ORBIT_AXIS_OPTIONS = [
        "Vertical (Z-axis)",
        "Horizontal (X-axis)",
        "Horizontal (Y-axis)",
        "Camera Up Vector",
    ]

    # Background options
    BACKGROUND_OPTIONS = [
        "Black (Default)",
        "White",
        "Light Gray",
        "Dark Gray",
        "Gradient (White-Gray)",
        "Gradient (Black-Gray)",
    ]

    # Easing functions for smooth animations
    EASING_OPTIONS = [
        "Linear",
        "Ease In-Out (Smooth)",
        "Ease In",
        "Ease Out",
    ]

    def __init__(self, parent=None, plotter=None, view_name="View"):
        super().__init__(parent)
        self.parent_view = parent
        self.plotter = plotter
        self.view_name = view_name
        
        # Capture current camera position before dialog opens
        self._captured_camera = None
        self._captured_focal_point = None
        if plotter is not None:
            try:
                self._captured_camera = plotter.camera_position
                self._captured_focal_point = plotter.camera.focal_point
            except Exception:
                pass

        self._setup_ui()
        self._connect_signals()
        self._update_ui_state()

    def _setup_ui(self):
        """Set up the dialog user interface."""
        self.setWindowTitle(f"Create Animated GIF - {self.view_name}")
        self.setMinimumSize(950, 650)
        
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # Title
        title_label = QLabel(f"<h2>Create {self.view_name} Animation</h2>")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # Subtitle
        subtitle_label = QLabel(
            "<i>Create stunning animated GIFs to showcase your 3D geomodelling structures</i>"
        )
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setStyleSheet("color: gray; margin-bottom: 10px;")
        main_layout.addWidget(subtitle_label)

        # === Content Layout (2 Columns) ===
        content_layout = QHBoxLayout()
        
        # Left Column: Animation & Camera Settings
        left_layout = QVBoxLayout()
        self._create_animation_group(left_layout)
        self._create_camera_group(left_layout)
        left_layout.addStretch()
        content_layout.addLayout(left_layout)

        # Right Column: Output & Visual Settings
        right_layout = QVBoxLayout()
        self._create_output_group(right_layout)
        self._create_visual_group(right_layout)
        self._create_quality_group(right_layout)
        right_layout.addStretch()
        content_layout.addLayout(right_layout)

        main_layout.addLayout(content_layout)

        # === Buttons ===
        self._create_buttons(main_layout)

    def _create_animation_group(self, parent_layout):
        """Create the animation settings group."""
        group = QGroupBox("Animation Settings")
        form = QFormLayout(group)

        # Animation preset
        self.animation_combo = QComboBox()
        for name, _, _ in self.ANIMATION_PRESETS:
            self.animation_combo.addItem(name)
        self.animation_combo.setCurrentIndex(0)  # Default to full orbit
        self.animation_combo.setToolTip(
            "Select an animation type:\n"
            "• Orbit: Camera rotates around the model\n"
            "• Oscillate: Camera swings back and forth\n"
            "• Tilt: Camera tilts up and down\n"
            "• Zoom: Camera zooms in then out\n"
            "• Turntable: Classic rotation around vertical axis"
        )
        form.addRow("Animation Type:", self.animation_combo)

        # Custom angle (for custom orbit)
        self.custom_angle_spin = QSpinBox()
        self.custom_angle_spin.setRange(10, 720)
        self.custom_angle_spin.setValue(360)
        self.custom_angle_spin.setSuffix("°")
        self.custom_angle_spin.setToolTip("Total rotation angle for custom orbit")
        self.custom_angle_spin.setEnabled(False)
        form.addRow("Custom Angle:", self.custom_angle_spin)

        # Duration
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(0.5, 30.0)
        self.duration_spin.setValue(4.0)
        self.duration_spin.setSingleStep(0.5)
        self.duration_spin.setSuffix(" seconds")
        self.duration_spin.setToolTip("Total duration of the animation")
        form.addRow("Duration:", self.duration_spin)

        # Frame rate
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(5, 60)
        self.fps_spin.setValue(20)
        self.fps_spin.setSuffix(" fps")
        self.fps_spin.setToolTip(
            "Frames per second. Higher values = smoother animation but larger file size.\n"
            "Recommended: 15-20 fps for web, 24-30 fps for presentations"
        )
        form.addRow("Frame Rate:", self.fps_spin)

        # Easing
        self.easing_combo = QComboBox()
        self.easing_combo.addItems(self.EASING_OPTIONS)
        self.easing_combo.setCurrentIndex(1)  # Default to smooth
        self.easing_combo.setToolTip(
            "Easing controls animation smoothness:\n"
            "• Linear: Constant speed\n"
            "• Ease In-Out: Smooth start and end (recommended)\n"
            "• Ease In: Starts slow, accelerates\n"
            "• Ease Out: Starts fast, decelerates"
        )
        form.addRow("Easing:", self.easing_combo)

        # Loop type
        self.loop_check = QCheckBox("Loop animation (ping-pong)")
        self.loop_check.setChecked(False)
        self.loop_check.setToolTip(
            "If checked, animation plays forward then backward for seamless looping"
        )
        form.addRow("", self.loop_check)

        parent_layout.addWidget(group)

    def _create_camera_group(self, parent_layout):
        """Create the camera/orbit settings group."""
        group = QGroupBox("Camera Settings")
        form = QFormLayout(group)

        # Orbit axis
        self.axis_combo = QComboBox()
        self.axis_combo.addItems(self.ORBIT_AXIS_OPTIONS)
        self.axis_combo.setToolTip(
            "Select the axis around which the camera will orbit:\n"
            "• Vertical (Z): Standard turntable rotation\n"
            "• Horizontal (X/Y): Side-to-side or front-to-back rotation\n"
            "• Camera Up: Orbit around current camera orientation"
        )
        form.addRow("Orbit Axis:", self.axis_combo)

        # Rotation direction
        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["Clockwise", "Counter-clockwise"])
        self.direction_combo.setToolTip("Direction of camera rotation")
        form.addRow("Direction:", self.direction_combo)

        # Elevation offset
        self.elevation_spin = QSpinBox()
        self.elevation_spin.setRange(-60, 60)
        self.elevation_spin.setValue(0)
        self.elevation_spin.setSuffix("°")
        self.elevation_spin.setToolTip(
            "Additional elevation angle above/below the horizontal plane"
        )
        form.addRow("Elevation Offset:", self.elevation_spin)

        # Zoom factor (for zoom animation)
        self.zoom_factor_spin = QDoubleSpinBox()
        self.zoom_factor_spin.setRange(1.1, 5.0)
        self.zoom_factor_spin.setValue(2.0)
        self.zoom_factor_spin.setSingleStep(0.1)
        self.zoom_factor_spin.setSuffix("x")
        self.zoom_factor_spin.setToolTip("Maximum zoom factor for zoom animation")
        form.addRow("Zoom Factor:", self.zoom_factor_spin)

        # Reset to current view
        reset_btn = QPushButton("Use Current View as Start")
        reset_btn.clicked.connect(self._reset_to_current_view)
        reset_btn.setToolTip("Set the current camera view as the animation starting point")
        form.addRow("", reset_btn)

        parent_layout.addWidget(group)

    def _create_output_group(self, parent_layout):
        """Create the output settings group."""
        group = QGroupBox("Output Settings")
        form = QFormLayout(group)

        # Resolution preset
        self.resolution_combo = QComboBox()
        for name, _, _ in self.RESOLUTION_PRESETS:
            self.resolution_combo.addItem(name)
        self.resolution_combo.setCurrentIndex(1)  # Default to HD Ready
        form.addRow("Resolution:", self.resolution_combo)

        # Width
        self.width_spin = QSpinBox()
        self.width_spin.setRange(200, 4096)
        self.width_spin.setValue(1280)
        self.width_spin.setSuffix(" px")
        self.width_spin.setEnabled(False)
        form.addRow("Width:", self.width_spin)

        # Height
        self.height_spin = QSpinBox()
        self.height_spin.setRange(200, 4096)
        self.height_spin.setValue(720)
        self.height_spin.setSuffix(" px")
        self.height_spin.setEnabled(False)
        form.addRow("Height:", self.height_spin)

        # Estimated info
        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: gray; font-style: italic;")
        self._update_info_label()
        form.addRow("", self.info_label)

        parent_layout.addWidget(group)

    def _create_visual_group(self, parent_layout):
        """Create the visual settings group."""
        group = QGroupBox("Visual Settings")
        form = QFormLayout(group)

        # Background color
        self.background_combo = QComboBox()
        self.background_combo.addItems(self.BACKGROUND_OPTIONS)
        form.addRow("Background:", self.background_combo)

        # Show axes
        self.show_axes_check = QCheckBox("Show coordinate axes")
        self.show_axes_check.setChecked(False)
        form.addRow("", self.show_axes_check)

        # Show bounding box
        self.show_bounds_check = QCheckBox("Show bounding box")
        self.show_bounds_check.setChecked(False)
        form.addRow("", self.show_bounds_check)

        # Colormap selection
        self.colormap_combo = QComboBox()
        self.colormap_combo.addItem("(Use Current)")
        self.colormap_combo.addItems(PropertiesCMaps.colormaps_list)
        self.colormap_combo.setEditable(True)
        self.colormap_combo.setToolTip(
            "Select a colormap to apply to scalar properties.\n"
            "Choose '(Use Current)' to keep existing colormaps."
        )
        form.addRow("Colormap:", self.colormap_combo)

        # Show scalar bar
        self.show_scalar_bar_check = QCheckBox("Show scalar bar (colorbar)")
        self.show_scalar_bar_check.setChecked(False)
        form.addRow("", self.show_scalar_bar_check)

        parent_layout.addWidget(group)

    def _create_quality_group(self, parent_layout):
        """Create the quality settings group."""
        group = QGroupBox("Quality Settings")
        form = QFormLayout(group)

        # Anti-aliasing
        self.aa_check = QCheckBox("Anti-aliasing (smoother edges)")
        self.aa_check.setChecked(True)
        form.addRow("", self.aa_check)

        # AA samples
        self.aa_samples_spin = QSpinBox()
        self.aa_samples_spin.setRange(1, 8)
        self.aa_samples_spin.setValue(4)
        self.aa_samples_spin.setToolTip(
            "Number of anti-aliasing samples (higher = smoother but slower)"
        )
        form.addRow("AA Samples:", self.aa_samples_spin)

        # Line width scale
        self.line_scale_spin = QDoubleSpinBox()
        self.line_scale_spin.setRange(0.5, 5.0)
        self.line_scale_spin.setValue(1.5)
        self.line_scale_spin.setSingleStep(0.5)
        self.line_scale_spin.setSuffix("x")
        self.line_scale_spin.setToolTip("Scale factor for line widths")
        form.addRow("Line Scale:", self.line_scale_spin)

        # Point size scale
        self.point_scale_spin = QDoubleSpinBox()
        self.point_scale_spin.setRange(0.5, 5.0)
        self.point_scale_spin.setValue(1.5)
        self.point_scale_spin.setSingleStep(0.5)
        self.point_scale_spin.setSuffix("x")
        self.point_scale_spin.setToolTip("Scale factor for point sizes")
        form.addRow("Point Scale:", self.point_scale_spin)

        # GIF optimization
        self.optimize_check = QCheckBox("Optimize GIF file size")
        self.optimize_check.setChecked(True)
        self.optimize_check.setToolTip(
            "Apply optimization to reduce GIF file size.\n"
            "May slightly reduce quality but significantly reduces file size."
        )
        form.addRow("", self.optimize_check)

        parent_layout.addWidget(group)

    def _create_buttons(self, parent_layout):
        """Create the dialog buttons."""
        button_layout = QHBoxLayout()

        # Preview button
        preview_btn = QPushButton("Preview First Frame")
        preview_btn.clicked.connect(self._show_preview)
        button_layout.addWidget(preview_btn)

        button_layout.addStretch()

        # Export button
        export_btn = QPushButton("Create GIF")
        export_btn.setStyleSheet(
            "background-color: #2E7D32; color: white; "
            "font-weight: bold; padding: 8px 16px;"
        )
        export_btn.clicked.connect(self._export_gif)
        button_layout.addWidget(export_btn)

        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        parent_layout.addLayout(button_layout)

    def _connect_signals(self):
        """Connect widget signals to handlers."""
        self.animation_combo.currentIndexChanged.connect(self._on_animation_changed)
        self.resolution_combo.currentIndexChanged.connect(self._on_resolution_changed)
        self.duration_spin.valueChanged.connect(self._update_info_label)
        self.fps_spin.valueChanged.connect(self._update_info_label)
        self.width_spin.valueChanged.connect(self._update_info_label)
        self.height_spin.valueChanged.connect(self._update_info_label)

    def _update_ui_state(self):
        """Update UI element states based on current selections."""
        self._on_animation_changed(self.animation_combo.currentIndex())
        self._on_resolution_changed(self.resolution_combo.currentIndex())

    def _on_animation_changed(self, index):
        """Handle animation preset selection."""
        _, anim_type, _ = self.ANIMATION_PRESETS[index]
        
        # Enable/disable custom angle based on animation type
        is_custom = anim_type == "custom"
        self.custom_angle_spin.setEnabled(is_custom)
        
        # Enable/disable zoom factor based on animation type
        is_zoom = anim_type == "zoom"
        self.zoom_factor_spin.setEnabled(is_zoom)
        
        # Enable/disable direction for oscillate animations
        is_oscillate = "oscillate" in anim_type
        # Direction still makes sense for oscillate
        
    def _on_resolution_changed(self, index):
        """Handle resolution preset selection."""
        if index < len(self.RESOLUTION_PRESETS) - 1:  # Not "Custom"
            _, width, height = self.RESOLUTION_PRESETS[index]
            self.width_spin.setValue(width)
            self.height_spin.setValue(height)
            self.width_spin.setEnabled(False)
            self.height_spin.setEnabled(False)
        else:
            self.width_spin.setEnabled(True)
            self.height_spin.setEnabled(True)
        self._update_info_label()

    def _update_info_label(self):
        """Update the information label with estimated values."""
        duration = self.duration_spin.value()
        fps = self.fps_spin.value()
        width = self.width_spin.value()
        height = self.height_spin.value()
        
        total_frames = int(duration * fps)
        if hasattr(self, 'loop_check') and self.loop_check.isChecked():
            total_frames = total_frames * 2 - 1
        
        # Rough estimate of file size (very approximate)
        estimated_size_mb = (total_frames * width * height * 0.5) / (1024 * 1024)
        if hasattr(self, 'optimize_check') and self.optimize_check.isChecked():
            estimated_size_mb *= 0.4
        
        self.info_label.setText(
            f"~{total_frames} frames | Est. size: {estimated_size_mb:.1f} MB"
        )

    def _reset_to_current_view(self):
        """Reset animation to start from current camera view."""
        if self.plotter is not None:
            try:
                self._captured_camera = self.plotter.camera_position
                self._captured_focal_point = self.plotter.camera.focal_point
                QMessageBox.information(
                    self,
                    "Camera Updated",
                    "Animation will now start from the current camera view."
                )
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Could not capture camera position: {str(e)}"
                )

    def _setup_export_plotter(self, plotter):
        """Configure the off-screen plotter for export.
        
        Args:
            plotter: PyVista Plotter to configure
        """
        # Background color
        bg_choice = self.background_combo.currentText()
        is_dark_bg = bg_choice in ["Black (Default)", "Dark Gray", "Gradient (Black-Gray)"]
        
        if bg_choice == "Black (Default)":
            plotter.set_background("black")
        elif bg_choice == "White":
            plotter.set_background("white")
        elif bg_choice == "Light Gray":
            plotter.set_background([0.9, 0.9, 0.9])
        elif bg_choice == "Dark Gray":
            plotter.set_background([0.2, 0.2, 0.2])
        elif bg_choice == "Gradient (White-Gray)":
            plotter.set_background("white", top=[0.85, 0.85, 0.9])
        elif bg_choice == "Gradient (Black-Gray)":
            plotter.set_background("black", top=[0.3, 0.3, 0.35])
        else:
            plotter.set_background("black")

        # Copy scale (vertical exaggeration) from source plotter
        if self.plotter is not None:
            try:
                scale = self.plotter.scale
                plotter.set_scale(xscale=scale[0], yscale=scale[1], zscale=scale[2])
            except Exception:
                pass

        text_color = "white" if is_dark_bg else "black"

        # Copy actors from source plotter
        self._copy_actors_to_plotter(plotter, is_dark_bg)

        # Reset camera to fit all actors, then apply captured position if available
        plotter.reset_camera()
        
        # Set initial camera position
        if self._captured_camera is not None:
            plotter.camera_position = self._captured_camera

        # Add axes if requested
        if self.show_axes_check.isChecked():
            plotter.add_axes(color=text_color)

        # Add bounding box if requested
        if self.show_bounds_check.isChecked():
            plotter.add_bounding_box(color=text_color)
        
        # Do initial render to ensure everything is set up
        plotter.render()

    def _copy_actors_to_plotter(self, target_plotter, is_dark_bg):
        """Copy actors from source plotter to target plotter.
        
        Args:
            target_plotter: The plotter to copy actors to
            is_dark_bg: Whether using a dark background
        """
        if self.plotter is None or not hasattr(self.plotter, "renderer"):
            return

        line_scale = self.line_scale_spin.value()
        point_scale = self.point_scale_spin.value()
        selected_cmap = self.colormap_combo.currentText()
        use_custom_cmap = selected_cmap != "(Use Current)"
        show_scalar_bar = self.show_scalar_bar_check.isChecked()

        text_color = "white" if is_dark_bg else "black"

        try:
            for uid, actor in self.plotter.renderer.actors.items():
                try:
                    if not hasattr(actor, "GetMapper") or actor.GetMapper() is None:
                        continue
                    
                    mapper = actor.GetMapper()
                    if mapper.GetInput() is None:
                        continue

                    # Wrap the data in PyVista
                    data = mapper.GetInput()
                    mesh = pv.wrap(data)

                    # Get actor properties
                    prop = actor.GetProperty()
                    color = prop.GetColor() if prop else (1, 1, 1)
                    opacity = prop.GetOpacity() if prop else 1.0
                    orig_line_width = prop.GetLineWidth() if prop else 1.0
                    orig_point_size = prop.GetPointSize() if prop else 5.0
                    representation = prop.GetRepresentation() if prop else 2
                    visibility = actor.GetVisibility()

                    if not visibility:
                        continue

                    # Scale line width and point size
                    scaled_line_width = max(orig_line_width * line_scale, 1.0)
                    scaled_point_size = max(orig_point_size * point_scale, 3.0)

                    # Determine style
                    style = "surface"
                    if representation == 0:
                        style = "points"
                    elif representation == 1:
                        style = "wireframe"

                    scalars, cmap, rgb, clim = self._get_actor_scalar_rendering(
                        actor_uid=uid,
                        mapper=mapper,
                        mesh=mesh,
                        use_custom_cmap=use_custom_cmap,
                        selected_cmap=selected_cmap,
                    )

                    # Add mesh to target plotter
                    target_plotter.add_mesh(
                        mesh,
                        color=color if scalars is None else None,
                        scalars=scalars,
                        cmap=cmap,
                        rgb=rgb,
                        clim=clim,
                        opacity=opacity,
                        style=style,
                        line_width=scaled_line_width,
                        point_size=scaled_point_size,
                        show_scalar_bar=show_scalar_bar and scalars is not None,
                        scalar_bar_args={
                            "color": text_color,
                        } if show_scalar_bar else None,
                    )
                except Exception:
                    # Skip actors that can't be copied
                    continue
        except Exception:
            pass

    @staticmethod
    def _normalize_property_name(prop_name):
        if prop_name is None:
            return None
        if isinstance(prop_name, str):
            prop_name = prop_name.strip()
            return None if prop_name.lower() == "none" or prop_name == "" else prop_name
        try:
            if np.isnan(prop_name):
                return None
        except Exception:
            pass
        return prop_name

    def _get_shown_property_for_actor(self, actor_uid):
        if self.parent_view is None or not hasattr(self.parent_view, "actors_df"):
            return None
        try:
            shown = self.parent_view.actors_df.loc[
                self.parent_view.actors_df["uid"] == actor_uid, "show_property"
            ]
            if len(shown) == 0:
                return None
            return self._normalize_property_name(shown.values[0])
        except Exception:
            return None

    def _get_property_cmap(self, property_name):
        property_name = self._normalize_property_name(property_name)
        if property_name is None:
            return None

        project_window = getattr(self.parent_view, "parent", None)
        if project_window is None or not hasattr(project_window, "prop_legend_df"):
            return None
        try:
            cmap_row = project_window.prop_legend_df.loc[
                project_window.prop_legend_df["property_name"] == property_name,
                "colormap",
            ]
            if len(cmap_row) == 0:
                return None
            cmap = cmap_row.values[0]
            if isinstance(cmap, str) and cmap.strip():
                return cmap
        except Exception:
            return None
        return None

    def _get_actor_scalar_rendering(
        self, actor_uid, mapper, mesh, use_custom_cmap, selected_cmap
    ):
        """Resolve scalar/rgb/cmap settings from the source actor mapper."""
        if mapper is None or not mapper.GetScalarVisibility():
            return None, None, False, None

        scalars = mapper.GetArrayName()
        if scalars and scalars not in mesh.array_names:
            scalars = None
        if scalars is None:
            scalars = mesh.active_scalars_name
        if scalars is None:
            return None, None, False, None

        rgb = False
        try:
            color_mode = mapper.GetColorModeAsString().lower()
            rgb = "direct" in color_mode
        except Exception:
            rgb = False

        if not rgb:
            try:
                scalar_values = mesh[scalars]
                if (
                    hasattr(scalar_values, "shape")
                    and len(scalar_values.shape) > 1
                    and scalar_values.shape[-1] in (3, 4)
                ):
                    rgb = True
            except Exception:
                pass

        cmap = None
        if not rgb:
            if use_custom_cmap:
                cmap = selected_cmap
            else:
                shown_property = self._get_shown_property_for_actor(actor_uid)
                cmap = self._get_property_cmap(shown_property)
                if cmap is None:
                    cmap = self._get_property_cmap(scalars)

        clim = None
        if not rgb:
            try:
                scalar_range = mapper.GetScalarRange()
                if scalar_range and len(scalar_range) == 2:
                    clim = scalar_range
            except Exception:
                pass

        return scalars, cmap, rgb, clim

    def _apply_easing(self, t, easing_type):
        """Apply easing function to normalized time value.
        
        Args:
            t: Normalized time value (0 to 1)
            easing_type: Type of easing to apply
            
        Returns:
            Eased time value
        """
        if easing_type == "Linear":
            return t
        elif easing_type == "Ease In-Out (Smooth)":
            # Smooth step (cubic)
            return t * t * (3 - 2 * t)
        elif easing_type == "Ease In":
            # Quadratic ease in
            return t * t
        elif easing_type == "Ease Out":
            # Quadratic ease out
            return t * (2 - t)
        else:
            return t

    def _generate_camera_path(self, plotter, num_frames):
        """Generate camera positions for the animation.
        
        Args:
            plotter: The PyVista plotter
            num_frames: Number of frames to generate
            
        Returns:
            List of camera positions (position, focal_point, view_up)
        """
        # Get animation settings
        anim_idx = self.animation_combo.currentIndex()
        _, anim_type, default_angle = self.ANIMATION_PRESETS[anim_idx]
        
        # Determine total angle
        if anim_type == "custom":
            total_angle = self.custom_angle_spin.value()
        else:
            total_angle = default_angle
        
        # Get direction
        clockwise = self.direction_combo.currentText() == "Clockwise"
        direction = 1 if clockwise else -1
        
        # Get orbit axis
        axis_choice = self.axis_combo.currentText()
        
        # Get easing type
        easing_type = self.easing_combo.currentText()
        
        # Get elevation offset
        elevation_offset = np.radians(self.elevation_spin.value())
        
        # Get zoom factor for zoom animation
        zoom_factor = self.zoom_factor_spin.value()
        
        # Get starting camera from the plotter (after setup)
        plotter.reset_camera()
        cam = plotter.camera
        
        # Use captured camera if available
        if self._captured_camera is not None:
            plotter.camera_position = self._captured_camera
            cam = plotter.camera
        
        # Get camera parameters
        focal_point = np.array(cam.focal_point)
        start_pos = np.array(cam.position)
        view_up = np.array(cam.up)
        
        camera_positions = []
        
        # Calculate camera radius from focal point
        camera_vector = start_pos - focal_point
        radius = np.linalg.norm(camera_vector)
        
        if radius < 1e-6:
            # Fallback if camera is at focal point
            radius = 1.0
            camera_vector = np.array([0, -radius, 0])
        
        # Normalize the camera vector for direction
        camera_dir = camera_vector / radius
        
        # Get initial spherical coordinates
        # Azimuth: angle in XY plane from X axis
        # Elevation: angle from XY plane
        initial_azimuth = np.arctan2(camera_dir[1], camera_dir[0])
        initial_elevation = np.arcsin(np.clip(camera_dir[2], -1, 1))
        
        for i in range(num_frames):
            # Normalized time (0 to 1)
            t = i / max(num_frames - 1, 1)
            
            # Apply easing
            eased_t = self._apply_easing(t, easing_type)
            
            if anim_type == "zoom":
                # Zoom animation: move camera closer then back
                zoom_t = np.sin(eased_t * np.pi)  # 0 -> 1 -> 0
                current_zoom = 1.0 / (1 + (zoom_factor - 1) * zoom_t)
                new_pos = focal_point + camera_vector * current_zoom
                camera_positions.append((tuple(new_pos), tuple(focal_point), tuple(view_up)))
                
            elif "oscillate" in anim_type:
                # Oscillating animation: swing back and forth
                swing_angle = np.radians(total_angle / 2) * direction
                angle = swing_angle * np.sin(eased_t * 2 * np.pi)
                
                if "Vertical" in axis_choice or "Up" in axis_choice:
                    new_azimuth = initial_azimuth + angle
                    new_elevation = initial_elevation + elevation_offset
                else:
                    new_azimuth = initial_azimuth
                    new_elevation = initial_elevation + angle
                
                # Calculate new position using spherical coordinates
                new_x = focal_point[0] + radius * np.cos(new_elevation) * np.cos(new_azimuth)
                new_y = focal_point[1] + radius * np.cos(new_elevation) * np.sin(new_azimuth)
                new_z = focal_point[2] + radius * np.sin(new_elevation)
                
                camera_positions.append(((new_x, new_y, new_z), tuple(focal_point), tuple(view_up)))
                
            elif "tilt" in anim_type:
                # Tilt animation: camera tilts up and down
                tilt_angle = np.radians(total_angle) * direction
                angle = tilt_angle * np.sin(eased_t * 2 * np.pi)
                
                new_azimuth = initial_azimuth
                new_elevation = initial_elevation + angle
                # Clamp elevation to avoid flipping
                new_elevation = np.clip(new_elevation, -np.pi/2 + 0.1, np.pi/2 - 0.1)
                
                new_x = focal_point[0] + radius * np.cos(new_elevation) * np.cos(new_azimuth)
                new_y = focal_point[1] + radius * np.cos(new_elevation) * np.sin(new_azimuth)
                new_z = focal_point[2] + radius * np.sin(new_elevation)
                
                camera_positions.append(((new_x, new_y, new_z), tuple(focal_point), tuple(view_up)))
                
            else:
                # Orbit/Turntable animation - rotate around the model
                angle_rad = np.radians(total_angle * eased_t) * direction
                
                if "Vertical" in axis_choice or "Up" in axis_choice:
                    # Rotate around Z axis (vertical turntable)
                    new_azimuth = initial_azimuth + angle_rad
                    new_elevation = initial_elevation + elevation_offset
                    
                    new_x = focal_point[0] + radius * np.cos(new_elevation) * np.cos(new_azimuth)
                    new_y = focal_point[1] + radius * np.cos(new_elevation) * np.sin(new_azimuth)
                    new_z = focal_point[2] + radius * np.sin(new_elevation)
                    
                elif "X-axis" in axis_choice:
                    # Rotate around X axis
                    cos_a = np.cos(angle_rad)
                    sin_a = np.sin(angle_rad)
                    
                    # Rotate camera_vector around X axis
                    rot_y = camera_vector[1] * cos_a - camera_vector[2] * sin_a
                    rot_z = camera_vector[1] * sin_a + camera_vector[2] * cos_a
                    
                    new_x = focal_point[0] + camera_vector[0]
                    new_y = focal_point[1] + rot_y
                    new_z = focal_point[2] + rot_z
                    
                else:  # Y-axis
                    # Rotate around Y axis
                    cos_a = np.cos(angle_rad)
                    sin_a = np.sin(angle_rad)
                    
                    # Rotate camera_vector around Y axis
                    rot_x = camera_vector[0] * cos_a + camera_vector[2] * sin_a
                    rot_z = -camera_vector[0] * sin_a + camera_vector[2] * cos_a
                    
                    new_x = focal_point[0] + rot_x
                    new_y = focal_point[1] + camera_vector[1]
                    new_z = focal_point[2] + rot_z
                
                camera_positions.append(((new_x, new_y, new_z), tuple(focal_point), tuple(view_up)))
        
        # Handle ping-pong looping
        if hasattr(self, 'loop_check') and self.loop_check.isChecked():
            # Add reversed frames (excluding first and last to avoid duplication)
            camera_positions = camera_positions + camera_positions[-2:0:-1]
        
        return camera_positions

    def _show_preview(self):
        """Show a preview of the first frame."""
        try:
            # Create preview at reduced resolution
            preview_width = min(640, self.width_spin.value())
            preview_height = int(preview_width * self.height_spin.value() / self.width_spin.value())

            preview_plotter = pv.Plotter(
                off_screen=True,
                window_size=[preview_width, preview_height],
            )

            self._setup_export_plotter(preview_plotter)

            # Take screenshot
            img = preview_plotter.screenshot(return_img=True)
            preview_plotter.close()

            # Show preview dialog
            preview_dialog = QDialog(self)
            preview_dialog.setWindowTitle("Animation Preview - First Frame")
            preview_dialog.setMinimumSize(preview_width + 40, preview_height + 80)

            layout = QVBoxLayout(preview_dialog)

            # Info label
            info = QLabel(f"Preview of first frame at {preview_width}×{preview_height}")
            info.setAlignment(Qt.AlignCenter)
            info.setStyleSheet("color: gray;")
            layout.addWidget(info)

            # Convert numpy array to QPixmap
            img = np.ascontiguousarray(img)
            height, width, channels = img.shape
            bytes_per_line = channels * width
            q_img = QImage(img.data, width, height, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img)

            label = QLabel()
            label.setPixmap(pixmap)
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(preview_dialog.close)
            layout.addWidget(close_btn)

            preview_dialog.exec()

        except Exception as e:
            QMessageBox.warning(
                self,
                "Preview Failed",
                f"Could not generate preview:\n{str(e)}"
            )

    def _export_gif(self):
        """Export the animated GIF."""
        # Default filename
        default_name = f"pzero_{self.view_name.lower().replace(' ', '_')}_animation.gif"

        # Ask for save location
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Animated GIF",
            default_name,
            "GIF files (*.gif);;All files (*.*)"
        )

        if not file_path:
            return
        
        # Ensure .gif extension
        if not file_path.lower().endswith('.gif'):
            file_path += '.gif'

        try:
            # Get settings
            width = self.width_spin.value()
            height = self.height_spin.value()
            duration = self.duration_spin.value()
            fps = self.fps_spin.value()
            num_frames = int(duration * fps)
            
            # Create progress dialog
            progress = QProgressDialog(
                "Creating animated GIF...",
                "Cancel",
                0, num_frames + 2,
                self
            )
            progress.setWindowTitle("Exporting Animation")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            
            # Create off-screen plotter
            export_plotter = pv.Plotter(
                off_screen=True,
                window_size=[width, height],
            )
            
            # Apply anti-aliasing
            if self.aa_check.isChecked():
                export_plotter.enable_anti_aliasing(
                    "ssaa",
                    multi_samples=self.aa_samples_spin.value()
                )
            
            # Setup the plotter
            self._setup_export_plotter(export_plotter)
            
            # Generate camera path
            camera_positions = self._generate_camera_path(export_plotter, num_frames)
            
            # Collect frames
            frames = []
            
            for i, cam_pos in enumerate(camera_positions):
                if progress.wasCanceled():
                    export_plotter.close()
                    return
                
                progress.setValue(i)
                progress.setLabelText(f"Rendering frame {i + 1} of {len(camera_positions)}...")
                
                # Set camera position
                export_plotter.camera_position = cam_pos
                
                # Force render update - this is critical!
                export_plotter.render()
                
                # Capture frame
                frame = export_plotter.screenshot(return_img=True)
                frames.append(frame)
            
            export_plotter.close()
            
            progress.setLabelText("Assembling GIF...")
            progress.setValue(num_frames)
            
            # Try to use imageio for GIF creation
            try:
                import imageio.v3 as iio
                
                # Calculate frame duration in milliseconds
                frame_duration = int(1000 / fps)
                
                # Write GIF
                iio.imwrite(
                    file_path,
                    frames,
                    duration=frame_duration,
                    loop=0,  # Infinite loop
                )
                
            except ImportError:
                # Fallback to PIL/Pillow
                try:
                    from PIL import Image
                    
                    # Convert frames to PIL Images
                    pil_frames = [Image.fromarray(f) for f in frames]
                    
                    # Calculate frame duration in milliseconds
                    frame_duration = int(1000 / fps)
                    
                    # Save as GIF
                    pil_frames[0].save(
                        file_path,
                        save_all=True,
                        append_images=pil_frames[1:],
                        duration=frame_duration,
                        loop=0,
                        optimize=self.optimize_check.isChecked(),
                    )
                    
                except ImportError:
                    raise ImportError(
                        "Neither 'imageio' nor 'Pillow' is installed.\n"
                        "Please install one of them: pip install imageio pillow"
                    )
            
            progress.setValue(num_frames + 2)
            progress.close()
            
            # Calculate file size
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            
            QMessageBox.information(
                self,
                "Export Successful",
                f"Animation exported to:\n{file_path}\n\n"
                f"Resolution: {width} × {height} pixels\n"
                f"Frames: {len(frames)}\n"
                f"Duration: {len(frames) / fps:.1f} seconds\n"
                f"File size: {file_size_mb:.2f} MB"
            )

            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export animation:\n{str(e)}"
            )
