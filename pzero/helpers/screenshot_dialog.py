"""screenshot_dialog.py
PZero© Andrea Bistacchi

High-quality screenshot export dialog with resolution presets, format options,
view settings, and colormap selection.
"""

import numpy as np

from PySide6.QtCore import Qt
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
)

import pyvista as pv

from ..properties_manager import PropertiesCMaps


class ScreenshotExportDialog(QDialog):
    """Dialog for exporting high-quality screenshots from PZero views.
    
    This dialog provides comprehensive options for exporting publication-quality
    figures including resolution presets, format selection, view settings,
    colormap options, and quality settings.
    
    Args:
        parent: The parent view window (ViewVTK subclass)
        plotter: The PyVista plotter to capture
        view_name: Name of the view for default filename (e.g., "3D", "Map", "XSection")
    """

    # Resolution presets: (name, width, height)
    RESOLUTION_PRESETS = [
        ("HD (1920×1080)", 1920, 1080),
        ("2K (2560×1440)", 2560, 1440),
        ("4K (3840×2160)", 3840, 2160),
        ("Print 300dpi A4 (3508×2480)", 3508, 2480),
        ("Print 300dpi Letter (3300×2550)", 3300, 2550),
        ("Print 600dpi (6000×4800)", 6000, 4800),
        ("Custom", 0, 0),
    ]

    # Output format options: (display_name, extension, filter_string)
    FORMAT_OPTIONS = [
        ("PNG (Recommended)", "png", "PNG files (*.png)"),
        ("JPEG", "jpg", "JPEG files (*.jpg *.jpeg)"),
        ("TIFF", "tiff", "TIFF files (*.tiff *.tif)"),
        ("PDF (Vector)", "pdf", "PDF files (*.pdf)"),
        ("SVG (Vector)", "svg", "SVG files (*.svg)"),
        ("EPS (Vector)", "eps", "EPS files (*.eps)"),
    ]

    # Background options
    BACKGROUND_OPTIONS = [
        "Black (Default)",
        "White",
        "Light Gray",
        "Dark Gray",
        "Gradient (White-Gray)",
        "Gradient (Black-Gray)",
        "Transparent",
    ]

    # Camera view presets
    VIEW_PRESETS = [
        "Current View",
        "Isometric",
        "Top (XY)",
        "Front (XZ)",
        "Side (YZ)",
        "Perspective 45°",
    ]

    def __init__(self, parent=None, plotter=None, view_name="View"):
        super().__init__(parent)
        self.parent_view = parent
        self.plotter = plotter
        self.view_name = view_name
        
        # Capture current camera position before dialog opens
        self._captured_camera = None
        if plotter is not None:
            try:
                self._captured_camera = plotter.camera_position
            except Exception:
                pass

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the dialog user interface."""
        self.setWindowTitle(f"Export Screenshot - {self.view_name}")
        self.setMinimumSize(900, 550)
        
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # Title
        title_label = QLabel(f"<h2>Export {self.view_name} Screenshot</h2>")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # === Content Layout (2 Columns) ===
        content_layout = QHBoxLayout()
        
        # Left Column: Primary Output Settings
        left_layout = QVBoxLayout()
        self._create_resolution_group(left_layout)
        self._create_format_group(left_layout)
        self._create_title_group(left_layout)
        left_layout.addStretch()
        content_layout.addLayout(left_layout)

        # Right Column: Visual & Quality Settings
        right_layout = QVBoxLayout()
        self._create_view_group(right_layout)
        self._create_colormap_group(right_layout)
        self._create_quality_group(right_layout)
        right_layout.addStretch()
        content_layout.addLayout(right_layout)

        main_layout.addLayout(content_layout)

        # === Buttons ===
        self._create_buttons(main_layout)

    def _create_resolution_group(self, parent_layout):
        """Create the image resolution settings group."""
        group = QGroupBox("Image Resolution")
        form = QFormLayout(group)

        # Preset selector
        self.preset_combo = QComboBox()
        for name, _, _ in self.RESOLUTION_PRESETS:
            self.preset_combo.addItem(name)
        self.preset_combo.setCurrentIndex(3)  # Default to Print 300dpi A4
        form.addRow("Preset:", self.preset_combo)

        # Width
        self.width_spin = QSpinBox()
        self.width_spin.setRange(100, 10000)
        self.width_spin.setValue(3508)
        self.width_spin.setSuffix(" px")
        form.addRow("Width:", self.width_spin)

        # Height
        self.height_spin = QSpinBox()
        self.height_spin.setRange(100, 8000)
        self.height_spin.setValue(2480)
        self.height_spin.setSuffix(" px")
        form.addRow("Height:", self.height_spin)

        # Transparent background checkbox
        self.transparent_check = QCheckBox("Transparent background")
        self.transparent_check.setChecked(False)
        form.addRow("", self.transparent_check)

        parent_layout.addWidget(group)

    def _create_format_group(self, parent_layout):
        """Create the output format settings group."""
        group = QGroupBox("Output Format")
        form = QFormLayout(group)

        # Format selector
        self.format_combo = QComboBox()
        for name, _, _ in self.FORMAT_OPTIONS:
            self.format_combo.addItem(name)
        form.addRow("Format:", self.format_combo)

        # DPI for vector formats
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(300)
        self.dpi_spin.setToolTip("DPI setting for PDF/SVG/EPS vector formats")
        form.addRow("DPI (for vectors):", self.dpi_spin)

        parent_layout.addWidget(group)

    def _create_view_group(self, parent_layout):
        """Create the view settings group."""
        group = QGroupBox("View Settings")
        form = QFormLayout(group)

        # Camera view preset
        self.view_combo = QComboBox()
        self.view_combo.addItems(self.VIEW_PRESETS)
        form.addRow("Camera View:", self.view_combo)

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

        parent_layout.addWidget(group)

    def _create_colormap_group(self, parent_layout):
        """Create the colormap settings group."""
        group = QGroupBox("Colormap Settings")
        form = QFormLayout(group)

        # Get colormaps from PropertiesCMaps
        self.colormap_combo = QComboBox()
        self.colormap_combo.addItem("(Use Current)")
        self.colormap_combo.addItems(PropertiesCMaps.colormaps_list)
        self.colormap_combo.setEditable(True)
        self.colormap_combo.setToolTip(
            "Select a colormap to apply to scalar properties in the export.\n"
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
        self.aa_samples_spin.setRange(1, 16)
        self.aa_samples_spin.setValue(8)
        self.aa_samples_spin.setToolTip("Number of anti-aliasing samples (higher = smoother)")
        form.addRow("AA Samples:", self.aa_samples_spin)

        # Line width scale
        self.line_scale_spin = QDoubleSpinBox()
        self.line_scale_spin.setRange(0.5, 10.0)
        self.line_scale_spin.setValue(2.0)
        self.line_scale_spin.setSingleStep(0.5)
        self.line_scale_spin.setSuffix("x")
        self.line_scale_spin.setToolTip("Scale factor for line widths in export")
        form.addRow("Line Width Scale:", self.line_scale_spin)

        # Point size scale
        self.point_scale_spin = QDoubleSpinBox()
        self.point_scale_spin.setRange(0.5, 10.0)
        self.point_scale_spin.setValue(2.0)
        self.point_scale_spin.setSingleStep(0.5)
        self.point_scale_spin.setSuffix("x")
        self.point_scale_spin.setToolTip("Scale factor for point sizes in export")
        form.addRow("Point Size Scale:", self.point_scale_spin)

        parent_layout.addWidget(group)

    def _create_title_group(self, parent_layout):
        """Create the title/annotation settings group."""
        group = QGroupBox("Title & Annotations")
        form = QFormLayout(group)

        # Title text
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Optional figure title")
        form.addRow("Title:", self.title_edit)

        # Font size
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 72)
        self.font_size_spin.setValue(16)
        form.addRow("Font Size:", self.font_size_spin)

        parent_layout.addWidget(group)

    def _create_buttons(self, parent_layout):
        """Create the dialog buttons."""
        button_layout = QHBoxLayout()

        # Preview button
        preview_btn = QPushButton("Preview")
        preview_btn.clicked.connect(self._show_preview)
        button_layout.addWidget(preview_btn)

        button_layout.addStretch()

        # Export button
        export_btn = QPushButton("Export Screenshot")
        export_btn.setStyleSheet(
            "background-color: #1565C0; color: white; "
            "font-weight: bold; padding: 8px 16px;"
        )
        export_btn.clicked.connect(self._export_screenshot)
        button_layout.addWidget(export_btn)

        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        parent_layout.addLayout(button_layout)

    def _connect_signals(self):
        """Connect widget signals to handlers."""
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        self.background_combo.currentTextChanged.connect(self._on_background_changed)

    def _on_preset_changed(self, index):
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

    def _on_background_changed(self, text):
        """Handle background selection changes."""
        if text == "Transparent":
            self.transparent_check.setChecked(True)
        else:
            self.transparent_check.setChecked(False)

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
        elif bg_choice == "Transparent":
            plotter.set_background("white")
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

        # Camera view
        view_choice = self.view_combo.currentText()
        self._apply_camera_view(plotter, view_choice)

        # Add axes if requested
        if self.show_axes_check.isChecked():
            plotter.add_axes(color=text_color)

        # Add bounding box if requested
        if self.show_bounds_check.isChecked():
            plotter.add_bounding_box(color=text_color)

        # Add title if provided
        title_text = self.title_edit.text().strip()
        if title_text:
            plotter.add_text(
                title_text,
                position="upper_edge",
                font_size=self.font_size_spin.value(),
                color=text_color,
            )

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

                    # Check for scalars
                    scalars = None
                    cmap = None
                    if mesh.n_arrays > 0:
                        scalars = mesh.active_scalars_name
                        if use_custom_cmap and scalars is not None:
                            cmap = selected_cmap

                    # Add mesh to target plotter
                    target_plotter.add_mesh(
                        mesh,
                        color=color if scalars is None else None,
                        scalars=scalars,
                        cmap=cmap,
                        opacity=opacity,
                        style=style,
                        line_width=scaled_line_width,
                        point_size=scaled_point_size,
                        show_scalar_bar=show_scalar_bar and scalars is not None,
                        scalar_bar_args={
                            "color": text_color,
                            "title_font_size": self.font_size_spin.value(),
                            "label_font_size": max(8, self.font_size_spin.value() - 4),
                        } if show_scalar_bar else None,
                    )
                except Exception:
                    # Skip actors that can't be copied
                    continue
        except Exception:
            pass

    def _apply_camera_view(self, plotter, view_choice):
        """Apply the selected camera view to the plotter.
        
        Args:
            plotter: The plotter to configure
            view_choice: The selected view preset
        """
        if view_choice == "Current View" and self._captured_camera is not None:
            plotter.camera_position = self._captured_camera
        elif view_choice == "Isometric":
            plotter.view_isometric()
        elif view_choice == "Top (XY)":
            plotter.view_xy()
        elif view_choice == "Front (XZ)":
            plotter.view_xz()
        elif view_choice == "Side (YZ)":
            plotter.view_yz()
        elif view_choice == "Perspective 45°":
            plotter.view_isometric()
            # Adjust for 45° perspective
            if self._captured_camera is not None:
                plotter.camera_position = self._captured_camera

    def _show_preview(self):
        """Show a preview of the screenshot."""
        try:
            # Create preview at reduced resolution
            preview_width = min(800, self.width_spin.value())
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
            preview_dialog.setWindowTitle("Screenshot Preview")
            preview_dialog.setMinimumSize(preview_width + 40, preview_height + 60)

            layout = QVBoxLayout(preview_dialog)

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

    def _export_screenshot(self):
        """Export the high-quality screenshot."""
        # Get format and extension
        format_idx = self.format_combo.currentIndex()
        format_name, ext, filter_str = self.FORMAT_OPTIONS[format_idx]

        # Default filename
        default_name = f"pzero_{self.view_name.lower().replace(' ', '_')}_screenshot.{ext}"

        # Ask for save location
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Screenshot",
            default_name,
            f"{filter_str};;All files (*.*)"
        )

        if not file_path:
            return

        try:
            # Create high-resolution off-screen plotter
            width = self.width_spin.value()
            height = self.height_spin.value()

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

            # Determine if transparent background
            use_transparent = (
                self.background_combo.currentText() == "Transparent"
                or self.transparent_check.isChecked()
            )

            # Export based on format
            if ext in ["pdf", "svg", "eps"]:
                # Vector formats
                export_plotter.save_graphic(file_path)
            else:
                # Raster formats
                export_plotter.screenshot(
                    file_path,
                    transparent_background=use_transparent,
                )

            export_plotter.close()

            QMessageBox.information(
                self,
                "Export Successful",
                f"Screenshot exported to:\n{file_path}\n\n"
                f"Resolution: {width} × {height} pixels\n"
                f"Format: {format_name}"
            )

            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export screenshot:\n{str(e)}"
            )

