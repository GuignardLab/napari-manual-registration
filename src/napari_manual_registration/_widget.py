import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import napari
import numpy as np
import tifffile
from magicgui.widgets import Container, EmptyWidget, Label, create_widget
from napari.qt.threading import thread_worker
from pyclesperanto_prototype import rotate as cl_rotate
from scipy.spatial.transform import Rotation as R
from scipy.ndimage import rotate as scipy_rotate
from scipy.ndimage import affine_transform as scipy_affine
from skimage.measure import regionprops
from qtpy.QtWidgets import QComboBox


class RegistrationWidget(Container):
    def __init__(self, viewer: "napari.viewer.Viewer"):
        super().__init__()

        self._viewer = viewer
        self._selected_directory = None
        self._layer_ref = create_widget(
            annotation="napari.layers.Layer", label="   Reference layer"
        )
        self._layer_ref.changed.connect(self._update_floating_choices)

        self._floating_data = None

        self._layer_floating = create_widget(
            annotation="napari.layers.Layer",
            label="   Layer to move",
            options={
                "choices": self._filter_ref_layer,
                "nullable": True,
                "value": None,
            },
        )
        self._layer_floating.changed.connect(self._store_data)

        self._toggle_bounding_boxes_checkox = create_widget(
            widget_type="CheckBox", label="Toggle bounding boxes"
        )
        self._toggle_bounding_boxes_checkox.changed.connect(
            self._toggle_bounding_boxes
        )

        self._debug_initial_only_checkbox = create_widget(
            widget_type="CheckBox",
            label="Debug: apply initial transform only",
            options={"value": False},
        )
        self._debug_initial_only_checkbox.visible = False

        self._format_layers_explicit_button = create_widget(
            widget_type="PushButton",
            label="Format layers",
        )
        self._format_layers_explicit_button.changed.connect(
            self._format_layer_for_explicit_registration
        )

        self._translate_rotation_offset = np.array([0, 0, 0])

        self._translate_z = create_widget(
            widget_type="IntSlider",
            label="   Trans Z",
            options={"min": -512, "max": 512},
        )
        self._translate_z.changed.connect(self._update_translation)
        self._translate_z.changed.connect(
            self._reset_transfos_if_layers_dont_exist
        )

        self._translate_y = create_widget(
            widget_type="IntSlider",
            label="   Trans Y",
            options={"min": -512, "max": 512},
        )
        self._translate_y.changed.connect(self._update_translation)
        self._translate_y.changed.connect(
            self._reset_transfos_if_layers_dont_exist
        )

        self._translate_x = create_widget(
            widget_type="IntSlider",
            label="   Trans X",
            options={"min": -512, "max": 512},
        )
        self._translate_x.changed.connect(self._update_translation)
        self._translate_x.changed.connect(
            self._reset_transfos_if_layers_dont_exist
        )

        # rotations
        self._scipy_rotation_checkbox = create_widget(
            widget_type="CheckBox",
            label="use scipy rotations (slower alternative)",
        )

        self._slider_rz = create_widget(
            widget_type="IntSlider",
            label="   Rot Z",
            options={"min": -180, "max": 180, "tracking": True},
        )
        self._slider_rz.changed.connect(self._update_rotation_worker)
        self._slider_rz.changed.connect(
            self._reset_transfos_if_layers_dont_exist
        )

        self._slider_ry = create_widget(
            widget_type="IntSlider",
            label="   Rot Y",
            options={"min": -180, "max": 180, "tracking": True},
        )
        self._slider_ry.changed.connect(self._update_rotation_worker)
        self._slider_ry.changed.connect(
            self._reset_transfos_if_layers_dont_exist
        )

        self._slider_rx = create_widget(
            widget_type="IntSlider",
            label="   Rot X",
            options={"min": -180, "max": 180, "tracking": True},
        )
        self._slider_rx.changed.connect(self._update_rotation_worker)
        self._slider_rx.changed.connect(
            self._reset_transfos_if_layers_dont_exist
        )

        self._create_landmarks_layers = create_widget(
            widget_type="PushButton", label="Create landmarks layer"
        )
        self._create_landmarks_layers.changed.connect(
            self._create_landmarks_layers_callback
        )
        self._landmarks_layer_ref = None
        self._landmarks_layer_floating = None

        self._format_layers_landmarks_button = create_widget(
            widget_type="PushButton",
            label="Format layers",
        )
        self._format_layers_landmarks_button.changed.connect(
            self._format_layer_for_landmarks_registration
        )

        self._run_landmarks_registration = create_widget(
            widget_type="PushButton", label="Run landmarks registration"
        )
        self._run_landmarks_registration.changed.connect(
            self._run_manual_registration_callback
        )

        self._modality_combo = QComboBox()
        self._modality_combo._explicitly_hidden = False
        self._modality_combo.native = self._modality_combo
        self._modality_combo.name = ""
        self._modality_combo.label = ""
        self._modality_combo.tooltip = ""
        self._modality_combo.addItems(
            [
                "Explicit transforms",
                "Landmarks matching",
                "Load from JSON",
            ]
        )
        self._modality_combo.currentTextChanged.connect(
            self._update_modality_visibility
        )
        self._modality_combo_container = Container(
            widgets=[self._modality_combo],
            labels=False,
        )
        self._modality_note_label = Label(
            value=(
                "<b>Use one modality at a time (explicit OR landmarks OR JSON):</b>"
            )
        )
        self._explicit_section_label = Label(
            value="<b>Explicit transforms</b>"
        )
        self._landmarks_section_label = Label(
            value="<b>Landmarks matching</b>"
        )

        self._load_json_path = create_widget(
            widget_type="FileEdit",
            label="Transform JSON",
            options={
                "mode": "r",
                "filter": "JSON files (*.json)",
            },
        )
        self._apply_json_button = create_widget(
            widget_type="PushButton",
            label="Apply JSON transform",
        )
        self._apply_json_button.clicked.connect(self._apply_json_transform)

        self._save_json_path = create_widget(
            widget_type="FileEdit",
            options={"mode": "d"},
        )

        self._save_json_button = create_widget(
            widget_type="PushButton", label="Save to JSON"
        )

        self._save_json_button.clicked.connect(self._save_to_json)

        self._save_mode = QComboBox()
        self._save_mode._explicitly_hidden = False
        self._save_mode.native = self._save_mode
        self._save_mode.name = ""
        self._save_mode.label = ""
        self._save_mode.tooltip = ""
        self._save_mode.addItems(
            [
                "Save parameters (JSON)",
                "Fuse views",
            ]
        )
        self._save_mode.currentTextChanged.connect(
            self._update_save_mode_visibility
        )
        self._save_mode_container = Container(
            widgets=[self._save_mode],
            labels=False,
        )
        self._save_mode_note = Label(
            value="Requires installing vt from the morpheme conda channel"
        )
        self._save_mode_note.visible = False
        self._save_section_label = Label(
            value="<b>Save transformation or fuse images:</b>"
        )

        self._fuse_output_path = create_widget(
            widget_type="FileEdit",
            label="Output folder",
            options={"mode": "d"},
        )
        self._fuse_output_name = create_widget(
            widget_type="LineEdit",
            label="Output name",
            options={"value": "fusion_registered.tif"},
        )
        self._fuse_add_to_napari = create_widget(
            widget_type="CheckBox",
            label="Load fused as layer",
        )
        self._run_fusion_button = create_widget(
            widget_type="PushButton", label="Run fusion"
        )
        self._run_fusion_button.clicked.connect(self._run_fusion)

        self._json_save_container = Container(
            widgets=[self._save_json_path, self._save_json_button],
            layout="horizontal",
        )
        self._fuse_row_bottom = Container(
            widgets=[self._fuse_add_to_napari, self._run_fusion_button],
            layout="horizontal",
        )
        self._fuse_container = Container(
            widgets=[
                self._fuse_output_path,
                self._fuse_output_name,
                self._fuse_row_bottom,
            ]
        )
        self._explicit_container = Container(
            widgets=[
                # self._explicit_section_label,
                self._format_layers_explicit_button,
                Label(value="Translations:"),
                self._translate_z,
                self._translate_y,
                self._translate_x,
                Label(value="Rotations:"),
                self._scipy_rotation_checkbox,
                self._slider_rz,
                self._slider_ry,
                self._slider_rx,
            ],
            labels=False,
        )
        self._landmarks_container = Container(
            widgets=[
                # self._landmarks_section_label,
                Label(value="Draw landmarks:"),
                self._create_landmarks_layers,
                self._format_layers_landmarks_button,
                self._run_landmarks_registration,
            ],
            labels=False,
        )
        self._json_container = Container(
            widgets=[
                Label(value="Load transform from JSON:"),
                self._load_json_path,
                self._apply_json_button,
            ],
            labels=False,
        )
        self._modality_section_container = Container(
            widgets=[
                self._modality_note_label,
                self._modality_combo_container,
                self._explicit_container,
                self._landmarks_container,
                self._json_container,
            ],
            labels=False,
        )
        self._save_section_container = Container(
            widgets=[
                self._save_section_label,
                self._save_mode_container,
                self._save_mode_note,
                self._json_save_container,
                self._fuse_container,
            ],
            labels=False,
        )

        # append into/extend the container with your widgets
        self.extend(
            [
                EmptyWidget(label="<b>Layers to register:</b>"),
                self._debug_initial_only_checkbox,
                self._layer_ref,
                self._layer_floating,
                self._toggle_bounding_boxes_checkox,
            ]
        )

        layout = self.native.layout()
        if hasattr(layout, "addRow"):
            layout.addRow(self._modality_section_container.native)
            layout.addRow(self._save_section_container.native)
        else:
            layout.addWidget(self._modality_section_container.native)
            layout.addWidget(self._save_section_container.native)

        self._update_save_mode_visibility(None)
        self._update_modality_visibility(None)

        self.worker = self._scipy_rotation_computer(self._viewer)
        self.worker.start()

    def _toggle_bounding_boxes(self, event):

        if self._layer_ref.value is None or self._layer_floating.value is None:
            napari.utils.notifications.show_warning(
                "Please select reference and floating layers first."
            )
            return

        self._layer_ref.value.bounding_box.visible = event
        self._layer_ref.value.bounding_box.opacity = 0.5
        self._layer_floating.value.bounding_box.visible = event
        self._layer_floating.value.bounding_box.opacity = 0.5

    def _format_layer_for_explicit_registration(self):

        if self._layer_ref.value is None or self._layer_floating.value is None:
            napari.utils.notifications.show_warning(
                "Please select reference and floating layers first."
            )
            return

        self._layer_ref.value.colormap = "cyan"
        self._layer_floating.value.colormap = "red"

        self._layer_ref.value.blending = "additive"
        self._layer_floating.value.blending = "additive"

        self._layer_ref.value.rendering = "attenuated_mip"
        self._layer_floating.value.rendering = "attenuated_mip"

        self._layer_ref.value.attenuation = 0.33
        self._layer_floating.value.attenuation = 0.33

        if (
            self._layer_ref.value.contrast_limits[0]
            == self._layer_ref.value.data.min()
        ):
            min_perc = np.percentile(self._layer_ref.value.data, 1)
            self._layer_ref.value.contrast_limits = (
                min_perc,
                self._layer_ref.value.contrast_limits[1],
            )
        if (
            self._layer_floating.value.contrast_limits[0]
            == self._layer_floating.value.data.min()
        ):
            min_perc = np.percentile(self._layer_floating.value.data, 1)
            self._layer_floating.value.contrast_limits = (
                min_perc,
                self._layer_floating.value.contrast_limits[1],
            )

        self._viewer.grid.enabled = False

        self._viewer.dims.ndisplay = 3
        self._viewer.camera.perspective = 10
        self._viewer.reset_view()
        self._viewer.camera.angles = (-20, 40, 150)

    def _format_layer_for_landmarks_registration(self):

        if self._layer_ref.value is None or self._layer_floating.value is None:
            napari.utils.notifications.show_warning(
                "Please select reference and floating layers first."
            )
            return

        if (
            self._landmarks_layer_ref is None
            or self._landmarks_layer_floating is None
        ):
            napari.utils.notifications.show_warning(
                "Please create landmarks layers first."
            )
            return

        if len(self._viewer.layers) != 4:
            napari.utils.notifications.show_warning(
                "Please remove other layers before running landmarks registration."
                "You should have only the reference, floating and associated landmarks layers."
            )
            return

        self._layer_ref.value.colormap = "cyan"
        self._layer_floating.value.colormap = "red"

        self._layer_ref.value.blending = "additive"
        self._layer_floating.value.blending = "additive"

        self._landmarks_layer_ref.n_edit_dimensions = 3
        self._landmarks_layer_floating.n_edit_dimensions = 3

        # Move layers in layers list
        layers_names = [layer.name for layer in self._viewer.layers]
        current_indices = [
            layers_names.index(self._layer_ref.value.name),
            layers_names.index(self._landmarks_layer_ref.name),
            layers_names.index(self._layer_floating.value.name),
            layers_names.index(self._landmarks_layer_floating.name),
        ]
        self._viewer.layers.move_multiple(current_indices)

        self._viewer.grid.enabled = True
        self._viewer.grid.shape = (1, 2)
        self._viewer.grid.stride = 2
        self._viewer.grid.enabled = False

        self._viewer.dims.ndisplay = 2
        self._viewer.reset_view()

    def _reset_transfos_if_layers_dont_exist(self, event):
        if self._layer_floating.value is None:
            # print('Layer not found, resetting sliders')
            self._slider_rz.value = 0
            self._slider_ry.value = 0
            self._slider_rx.value = 0
            self._translate_z.value = 0
            self._translate_y.value = 0
            self._translate_x.value = 0

    def _save_to_json(self):
        path = str(self._save_json_path.value)
        if path == "." or not os.path.exists(path):
            napari.utils.notifications.show_warning(
                "Please select a directory first."
            )
        else:
            # Example data to save into JSON
            data_to_save = {
                "rot_z": self._slider_rz.value,
                "rot_y": self._slider_ry.value,
                "rot_x": self._slider_rx.value,
                "trans_z": self._translate_z.value,
                "trans_y": self._translate_y.value,
                "trans_x": self._translate_x.value,
            }
            # Example file name
            file_name = "initial_transformation.json"
            file_path = os.path.join(path, file_name)

            with open(file_path, "w") as json_file:
                json.dump(data_to_save, json_file, indent=4)

            napari.utils.notifications.show_info(
                f"Transformation saved to {file_path}"
            )

    def _update_save_mode_visibility(self, event):
        mode = (
            self._save_mode.currentText()
            if hasattr(self._save_mode, "currentText")
            else self._save_mode.value
        )
        is_json = mode == "Save parameters (JSON)"
        self._json_save_container.visible = is_json
        self._fuse_container.visible = not is_json
        self._save_mode_note.visible = not is_json

    def _update_modality_visibility(self, event):
        mode = (
            self._modality_combo.currentText()
            if hasattr(self._modality_combo, "currentText")
            else self._modality_combo.value
        )
        is_explicit = mode == "Explicit transforms"
        is_landmarks = mode == "Landmarks matching"
        is_json = mode == "Load from JSON"
        self._explicit_container.visible = is_explicit
        self._landmarks_container.visible = is_landmarks
        self._json_container.visible = is_json

    def _get_layer_voxel_size(self, layer):
        if layer is None:
            return [1, 1, 1]
        scale = getattr(layer, "scale", None)
        if scale is None or len(scale) < 3:
            return [1, 1, 1]
        return [float(scale[2]), float(scale[1]), float(scale[0])]

    def _prepare_fusion_array(self, data, label):
        if data.dtype == np.bool_:
            napari.utils.notifications.show_warning(
                f"{label} layer is boolean; converting to uint16."
            )
            return data.astype(np.uint16)

        if np.issubdtype(data.dtype, np.floating):
            data_min = float(np.nanmin(data))
            data_max = float(np.nanmax(data))
            if data_min >= 0.0 and data_max <= 1.0:
                napari.utils.notifications.show_info(
                    f"{label} appears normalized in [0, 1]; scaling to uint16 for fusion."
                )
                return (data * np.iinfo(np.uint16).max).astype(np.uint16)
            napari.utils.notifications.show_warning(
                f"{label} is float; converting to uint16 for fusion."
            )
            data = np.clip(data, 0, np.iinfo(np.uint16).max)
            return data.astype(np.uint16)

        if data.dtype not in (np.int16, np.uint16):
            napari.utils.notifications.show_warning(
                f"{label} dtype {data.dtype} converted to uint16 for fusion."
            )
            data = np.clip(data, 0, np.iinfo(np.uint16).max)
            return data.astype(np.uint16)

        return data

    def _run_fusion(self):
        if self._layer_ref.value is None or self._layer_floating.value is None:
            napari.utils.notifications.show_warning(
                "Please select reference and floating layers first."
            )
            return

        output_dir = str(self._fuse_output_path.value)
        if output_dir == "." or not os.path.exists(output_dir):
            napari.utils.notifications.show_warning(
                "Please select a valid output directory first."
            )
            return

        output_name = str(self._fuse_output_name.value).strip()
        if output_name == "":
            napari.utils.notifications.show_warning(
                "Please provide a valid output file name."
            )
            return

        if not output_name.lower().endswith(".tif"):
            output_name = f"{output_name}.tif"

        try:
            from tapenade import reconstruction
        except Exception:
            napari.utils.notifications.show_error(
                "tapenade is not available. Please install it to run fusion."
            )
            return

        ref_data = self._prepare_fusion_array(
            self._layer_ref.value.data, "Reference"
        )
        float_data = self._prepare_fusion_array(
            self._layer_floating.value.data, "Floating"
        )
        if ref_data.ndim != 3 or float_data.ndim != 3:
            napari.utils.notifications.show_warning(
                "Fusion currently supports 3D volumes only."
            )
            return

        input_voxel = self._get_layer_voxel_size(self._layer_ref.value)
        output_voxel = input_voxel

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            sample_dir = temp_root / "sample"
            raw_dir = sample_dir / "raw"
            trsf_dir = sample_dir / "trsf"
            reg_dir = sample_dir / "registered"
            fused_dir = sample_dir / "fused"
            weights_dir = sample_dir / "weights"
            weights_before = weights_dir / "before_trsf"
            weights_after = weights_dir / "after_trsf"

            for path in [
                raw_dir,
                trsf_dir,
                reg_dir,
                fused_dir,
                weights_before,
                weights_after,
            ]:
                path.mkdir(parents=True, exist_ok=True)

            ref_name = "ref.tif"
            float_name = "float.tif"

            tifffile.imwrite(raw_dir / ref_name, ref_data)
            tifffile.imwrite(raw_dir / float_name, float_data)

            json_path = sample_dir / "initial_transformation.json"
            data_to_save = {
                "rot_z": self._slider_rz.value,
                "rot_y": self._slider_ry.value,
                "rot_x": self._slider_rx.value,
                "trans_z": self._translate_z.value,
                "trans_y": self._translate_y.value,
                "trans_x": self._translate_x.value,
            }
            with open(json_path, "w") as json_file:
                json.dump(data_to_save, json_file, indent=4)

            reconstruction.register(
                path_data=raw_dir,
                path_transformation=trsf_dir,
                path_registered_data=reg_dir,
                reference_image=ref_name,
                floating_image=float_name,
                input_voxel=input_voxel,
                output_voxel=output_voxel,
                compute_trsf=1,
                input_init_trsf_from_plugin=str(json_path),
                test_init=1 if self._debug_initial_only_checkbox.value else 0,
            )

            ref_registered_path = reg_dir / ref_name
            if not ref_registered_path.exists():
                shutil.copyfile(raw_dir / ref_name, ref_registered_path)

            if not self._debug_initial_only_checkbox.value:
                try:
                    refined_trans, refined_angles = (
                        reconstruction.compute_transformation_from_trsf_files(
                            trsf_dir
                        )
                    )
                    napari.utils.notifications.show_info(
                        "Refined transform (XYZ): "
                        f"trans={np.round(refined_trans, 3)}, "
                        f"rot_deg={np.round(refined_angles, 3)}"
                    )
                except Exception:
                    napari.utils.notifications.show_warning(
                        "Could not read refined transformation from trsf files."
                    )

            reconstruction.fuse_sides(
                folder=sample_dir,
                reference_image=ref_name,
                floating_image=float_name,
                folder_output=fused_dir,
                name_output=output_name,
                input_voxel=input_voxel,
                output_voxel=output_voxel,
            )

            output_path = Path(output_dir) / output_name
            shutil.copyfile(fused_dir / output_name, output_path)

        if self._fuse_add_to_napari.value:
            fused_data = tifffile.imread(Path(output_dir) / output_name)
            scale = (output_voxel[2], output_voxel[1], output_voxel[0])
            self._viewer.add_image(
                fused_data,
                name=f"fused_{self._layer_ref.value.name}",
                scale=scale,
            )

        napari.utils.notifications.show_info(
            f"Fused volume saved to {Path(output_dir) / output_name}"
        )

    def _store_data(self, event):
        self._floating_data = self._layer_floating.value.data
        self._floating_initial_shape = np.array(
            self._layer_floating.value.data.shape
        )

    def _update_floating_choices(self, event):
        ref_choice = self._layer_ref.value
        self._layer_floating.choices = [
            layer
            for layer in self._viewer.layers
            if layer.name != ref_choice.name
        ]

    def _filter_ref_layer(self, event):
        ref_choice = self._layer_ref.value
        return [
            layer
            for layer in self._viewer.layers
            if layer.name != ref_choice.name
        ]

    def _slider_translation_vector(self):
        return np.array(
            [
                self._translate_z.value,
                self._translate_y.value,
                self._translate_x.value,
            ]
        )

    def _update_translation(self):

        translation = (
            self._translate_rotation_offset + self._slider_translation_vector()
        )
        if self._layer_floating.value is not None:
            self._layer_floating.value.translate = translation

        if self._landmarks_layer_floating is not None:
            self._landmarks_layer_floating.translate = translation

    @thread_worker
    def _scipy_rotation_computer(self, viewer):

        rotations = None

        while True:

            time.sleep(0.1)
            rotations = yield rotations

            if rotations is not None and self._floating_data is not None:
                if self._scipy_rotation_checkbox.value:
                    rotations = R.from_euler(
                        "XYZ", rotations, degrees=True
                    ).as_euler("xyz", degrees=True)

                    rot_mat = R.from_euler(
                        "XYZ", rotations, degrees=True
                    ).as_matrix()
                    center = np.array(self._floating_data.shape) / 2
                    translation = center - rot_mat @ center
                    affine = np.eye(4)
                    affine[:3, :3] = rot_mat
                    affine[:3, 3] = translation

                    rotated = scipy_affine(
                        self._floating_data,
                        affine[:3, :3],
                        offset=affine[:3, 3],
                        order=0,
                        prefilter=False,
                    )
                else:
                    rotations = R.from_euler(
                        "XYZ", rotations, degrees=True
                    ).as_euler("xyz", degrees=True)

                    rotated = cl_rotate(
                        source=self._floating_data,
                        angle_around_z_in_degrees=rotations[0],
                        angle_around_y_in_degrees=rotations[1],
                        angle_around_x_in_degrees=rotations[2],
                        rotate_around_center=True,
                        linear_interpolation=False,
                        auto_size=False,
                    )

                self._layer_floating.value.data = rotated

    def _update_rotation_worker(self, event):
        self.worker.send(
            (
                int(self._slider_rz.value),
                float(self._slider_ry.value),
                int(self._slider_rx.value),
            )
        )

    def _create_landmarks_layers_callback(self):

        if self._layer_ref.value is None or self._layer_floating.value is None:
            napari.utils.notifications.show_warning(
                "Please select reference and floating layers first."
            )
            return

        if self._landmarks_layer_ref is not None:
            try:
                self._viewer.layers.remove(self._landmarks_layer_ref)
            except ValueError:
                napari.utils.notifications.show_warning(
                    f"Layer {self._landmarks_layer_ref.name} not found"
                )

        self._landmarks_layer_ref = self._viewer.add_labels(
            np.zeros(self._layer_ref.value.data.shape, dtype=np.uint8),
            name="landmarks_ref",
        )

        if self._landmarks_layer_floating is not None:
            try:
                self._viewer.layers.remove(self._landmarks_layer_floating)
            except ValueError:
                napari.utils.notifications.show_warning(
                    f"Layer {self._landmarks_layer_floating.name} not found"
                )

        self._landmarks_layer_floating = self._viewer.add_labels(
            np.zeros(self._layer_floating.value.data.shape, dtype=np.uint8),
            name="landmarks_floating",
        )

    def _extract_landmarks(self, labels):
        #! TODO: make this compatible with more landmarks
        props = regionprops(labels)
        if len(props) != 3:
            msg = f"Expected 3 landmarks, found {len(props)}!"
            napari.utils.notifications.show_warning(msg)
            raise ValueError(msg)
        centroids = np.array([prop.centroid for prop in props]).T
        centermass = np.mean(centroids, axis=1)
        centroids_centered = centroids - centermass.reshape(3, 1)

        return centroids_centered, centermass

    def _run_manual_registration_callback(self):

        translation_vector, rotation_matrix = (
            self._find_optimal_transformation_from_landmarks()
        )

        center = np.array(self._layer_floating.value.data.shape) / 2
        self._translate_rotation_offset = (
            np.eye(3) - rotation_matrix
        ) @ center

        self._update_sliders(
            translation_vector - self._translate_rotation_offset,
            rotation_matrix,
        )

        self._layer_floating.value.rotate = rotation_matrix
        self._layer_floating.value.translate = translation_vector

        if self._landmarks_layer_floating is not None:
            self._landmarks_layer_floating.rotate = rotation_matrix
            self._landmarks_layer_floating.translate = translation_vector

    def _find_optimal_transformation_from_landmarks(self):

        landmarks_ref = self._landmarks_layer_ref
        landmarks_floating = self._landmarks_layer_floating

        centroids_ref_centered, centermass_ref = self._extract_landmarks(
            landmarks_ref.data
        )
        centroids_float_centered, centermass_float = self._extract_landmarks(
            landmarks_floating.data
        )

        H = centroids_ref_centered @ np.transpose(centroids_float_centered)

        # find rotation
        U, _, Vt = np.linalg.svd(H)
        rotation_matrix = Vt.T @ U.T

        # special reflection case
        if np.linalg.det(rotation_matrix) < 0:
            print("det(R) < R, reflection detected!, correcting for it ...")
            Vt[2, :] *= -1
            rotation_matrix = Vt.T @ U.T

        translation_vector = (
            centermass_ref - rotation_matrix @ centermass_float
        )

        return translation_vector, rotation_matrix

    def _update_sliders(self, translation_vector, rotation_matrix):
        self._translate_z.value = translation_vector[0]
        self._translate_y.value = translation_vector[1]
        self._translate_x.value = translation_vector[2]

        angles = R.from_matrix(rotation_matrix).as_euler("xyz", degrees=True)

        self._slider_rz.value = angles[0]
        self._slider_ry.value = angles[1]
        self._slider_rx.value = angles[2]

    def _apply_json_transform(self):
        if self._layer_floating.value is None:
            napari.utils.notifications.show_warning(
                "Please select a layer to move first."
            )
            return

        json_path = str(self._load_json_path.value)
        if json_path == "." or not os.path.exists(json_path):
            napari.utils.notifications.show_warning(
                "Please select a valid JSON file first."
            )
            return

        try:
            with open(json_path, "r") as json_file:
                data = json.load(json_file)
        except Exception:
            napari.utils.notifications.show_error("Could not read JSON file.")
            return

        required_keys = {
            "rot_z",
            "rot_y",
            "rot_x",
            "trans_z",
            "trans_y",
            "trans_x",
        }
        if not required_keys.issubset(data.keys()):
            napari.utils.notifications.show_error(
                "JSON file does not contain expected transform keys."
            )
            return

        self._translate_rotation_offset = np.array([0, 0, 0])

        try:
            self._translate_z.value = float(data["trans_z"])
            self._translate_y.value = float(data["trans_y"])
            self._translate_x.value = float(data["trans_x"])
            self._slider_rz.value = float(data["rot_z"])
            self._slider_ry.value = float(data["rot_y"])
            self._slider_rx.value = float(data["rot_x"])
        except Exception:
            napari.utils.notifications.show_error(
                "JSON values must be numeric."
            )
            return

        self._update_translation()
        self._update_rotation_worker(None)

        napari.utils.notifications.show_info(
            "Applied JSON transform to floating layer."
        )


if __name__ == "__main__":
    viewer = napari.Viewer()
    widget = RegistrationWidget(viewer)
    viewer.window.add_dock_widget(widget, area="right")
    napari.run()
