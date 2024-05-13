import napari
import numpy as np
import tifffile
from magicgui import magicgui
from magicgui.widgets import Container, create_widget, EmptyWidget
from scipy.spatial.transform import Rotation as R
from scipy.ndimage import rotate
from skimage.measure import regionprops
from napari.qt.threading import thread_worker
import time
from pyclesperanto_prototype import rotate as cl_rotate


class RegistrationWidget(Container):
    def __init__(self, viewer: "napari.viewer.Viewer"):
        super().__init__()

        self._viewer = viewer

        self._layer_ref = create_widget(
            annotation="napari.layers.Layer", label="Reference layer"
        )
        self._layer_ref.changed.connect(self._update_floating_choices)


        self._floating_data = None

        self._layer_floating = create_widget(
            annotation="napari.layers.Layer", label="Layer to move",
            options={'choices': self._filter_ref_layer, 'nullable': True, 'value': None}
        )
        self._layer_floating.changed.connect(self._store_data)

        self._translate_rotation_offset = np.array([0,0,0])

        self._translate_z = create_widget(
            widget_type="IntSlider", label="tz",
            options={'min':-512, 'max':512}
        )
        self._translate_z.changed.connect(self._update_translation)

        self._translate_y = create_widget(
            widget_type="IntSlider", label="ty",
            options={'min':-512, 'max':512}
        )
        self._translate_y.changed.connect(self._update_translation)

        self._translate_x = create_widget(
            widget_type="IntSlider", label="tx",
            options={'min':-512, 'max':512}
        )
        self._translate_x.changed.connect(self._update_translation)

        self._rotate_z = create_widget(
            widget_type="IntSlider", label="rz",
            options={'min':-180, 'max':180}
        )
        self._rotate_z.changed.connect(self._update_rotation)

        self._rotate_y = create_widget(
            widget_type="IntSlider", label="ry",
            options={'min':-180, 'max':180}
        )
        self._rotate_y.changed.connect(self._update_rotation)
        # self._rotate_y.enabled = False

        self._rotate_x = create_widget(
            widget_type="IntSlider", label="rx",
            options={'min':-180, 'max':180}
        )
        self._rotate_x.changed.connect(self._update_rotation)
        # self._rotate_x.enabled = False

        self._create_landmarks_layers = create_widget(
            widget_type="PushButton", label="Create landmarks layer"
        )
        self._create_landmarks_layers.changed.connect(self._create_landmarks_layers_callback)
        self._landmarks_layer_ref = None
        self._landmarks_layer_floating = None

        self._run_landmarks_registration = create_widget(
            widget_type="PushButton", label="Run landmarks registration"
        )
        self._run_landmarks_registration.changed.connect(self._run_manual_registration_callback)

        self._test_button = create_widget(
            widget_type="PushButton", label="Test"
        )
        self._test_button.clicked.connect(self._test_callback)

        self._test_slider_rz = create_widget(
            widget_type="IntSlider", label="rz",
            options={'min':-180, 'max':180, 'tracking':True}
        )
        self._test_slider_rz.changed.connect(self._update_test_rotation)
        self._test_slider_ry = create_widget(
            widget_type="IntSlider", label="ry",
            options={'min':-180, 'max':180, 'tracking':True}
        )
        self._test_slider_ry.changed.connect(self._update_test_rotation)
        self._test_slider_rx = create_widget(
            widget_type="IntSlider", label="rx",
            options={'min':-180, 'max':180, 'tracking':True}
        )
        self._test_slider_rx.changed.connect(self._update_test_rotation)

        # append into/extend the container with your widgets
        self.extend(
            [
                self._layer_ref,
                self._layer_floating,
                self._translate_z,
                self._translate_y,
                self._translate_x,
                self._rotate_z,
                # self._rotate_y,
                # self._rotate_x,
                EmptyWidget(),
                EmptyWidget(),
                self._create_landmarks_layers,
                self._run_landmarks_registration,
                EmptyWidget(),
                EmptyWidget(),
                # self._test_button,
                self._test_slider_rz,
                self._test_slider_ry,
                self._test_slider_rx
            ]
        )

        self.worker = self._scipy_rotation_computer(self._viewer)
        self.worker.start()

    def _store_data(self, event):
        self._floating_data = self._layer_floating.value.data
        self._floating_initial_shape = np.array(self._layer_floating.value.data.shape)
    

    def _update_floating_choices(self, event):
        ref_choice = self._layer_ref.value
        self._layer_floating.choices = [layer for layer in self._viewer.layers if layer.name != ref_choice.name]

    def _filter_ref_layer(self, event):
        ref_choice = self._layer_ref.value
        return [layer for layer in self._viewer.layers if layer.name != ref_choice.name]

    def _test_callback(self):
        # self.extend(
        #     [
        #         self._layer_ref,
        #         self._layer_floating,
        #         self._translate_z,
        #         self._translate_y,
        #         self._translate_x,
        #         EmptyWidget(),
        #         EmptyWidget(),
        #         self._create_landmarks_layers,
        #         self._run_landmarks_registration,
        #         EmptyWidget(),
        #         EmptyWidget(),
        #         self._test_button,
        #         self._test_slider
        #     ]
        # )
        print(self._floating_data.shape)

    def _slider_translation_vector(self):
        return np.array([
            self._translate_z.value, 
            self._translate_y.value, 
            self._translate_x.value
        ])
    
    def _slider_rotation_matrix(self):
        return R.from_euler('xyz', [
            self._rotate_z.value,
            self._rotate_y.value,
            self._rotate_x.value
        ], degrees=True).as_matrix()

    def _update_translation(self):

        translation = self._translate_rotation_offset + self._slider_translation_vector()

        self._layer_floating.value.translate = translation
        
        if self._landmarks_layer_floating is not None:
            self._landmarks_layer_floating.translate = translation
        
    def _update_rotation(self):
        rotation = self._slider_rotation_matrix()

        # worker = self._scipy_rotation_computer(self._layer_floating.value.data, R.from_matrix(rotation).as_euler('xyz', degrees=True))
        # worker.yielded.connect(self._update_rotation_callback)

        self._layer_floating.value.rotate = rotation

        center = np.array(self._layer_floating.value.data.shape)/2
        self._translate_rotation_offset = (np.eye(3) - rotation) @ center

        translation = self._translate_rotation_offset + self._slider_translation_vector()

        self._layer_floating.value.translate = translation

        if self._landmarks_layer_floating is not None:
            self._landmarks_layer_floating.rotate = rotation
            self._landmarks_layer_floating.translate = translation

    def _create_landmarks_layers_callback(self):
        if self._landmarks_layer_ref is not None:
            try:
                self._viewer.layers.remove(self._landmarks_layer_ref)
            except ValueError:
                print(f'Layer {self._landmarks_layer_ref.name} not found')

        self._landmarks_layer_ref = self._viewer.add_labels(
            np.zeros(self._layer_ref.value.data.shape, dtype=np.uint8),
            name='landmarks_ref'
        )

        if self._landmarks_layer_floating is not None:
            try:
                self._viewer.layers.remove(self._landmarks_layer_floating)
            except ValueError:
                print(f'Layer {self._landmarks_layer_floating.name} not found')

        self._landmarks_layer_floating = self._viewer.add_labels(
            np.zeros(self._layer_floating.value.data.shape, dtype=np.uint8),
            name='landmarks_floating'
        )

    def _extract_landmarks(self, labels):
        props = regionprops(labels)
        assert len(props) == 3, f'Expected 3 landmarks, found {len(props)}'
        centroids = np.array([prop.centroid for prop in props]).T
        centermass = np.mean(centroids, axis=1)
        centroids_centered = centroids - centermass.reshape(3, 1)
 
        return centroids_centered, centermass
    
    def _update_sliders(self, translation_vector, rotation_matrix):
        self._translate_z.value = translation_vector[0]
        self._translate_y.value = translation_vector[1]
        self._translate_x.value = translation_vector[2]

        angles = R.from_matrix(rotation_matrix).as_euler('xyz', degrees=True)

        self._rotate_z.value = angles[0]
        self._rotate_y.value = angles[1]
        self._rotate_x.value = angles[2]

    def _run_manual_registration_callback(self):

        translation_vector, rotation_matrix = self._find_optimal_transformation_from_landmarks()

        center = np.array(self._layer_floating.value.data.shape)/2
        self._translate_rotation_offset = (np.eye(3) - rotation_matrix) @ center

        self._update_sliders(translation_vector - self._translate_rotation_offset, rotation_matrix)

        self._layer_floating.value.rotate = rotation_matrix
        self._layer_floating.value.translate = translation_vector

        if self._landmarks_layer_floating is not None:
            self._landmarks_layer_floating.rotate = rotation_matrix
            self._landmarks_layer_floating.translate = translation_vector


    def _update_test_rotation(self, event):
        self.worker.send(
            (
                self._test_slider_rz.value,
                self._test_slider_ry.value,
                self._test_slider_rx.value
            )
        )


    @thread_worker
    def _scipy_rotation_computer(self, viewer):

        rotations = None
        
        while True:

            rotations = yield rotations
            time.sleep(0.1)

            if rotations is not None and self._floating_data is not None:
                rotations = R.from_euler('XYZ', rotations, degrees=True).as_euler('xyz', degrees=True)
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

                


    def _find_optimal_transformation_from_landmarks(self):
        
        landmarks_ref = self._landmarks_layer_ref
        landmarks_floating = self._landmarks_layer_floating
        
        centroids_ref_centered, centermass_ref = self._extract_landmarks(landmarks_ref.data)
        centroids_float_centered, centermass_float = self._extract_landmarks(landmarks_floating.data)

        H = centroids_ref_centered @ np.transpose(centroids_float_centered)

        # find rotation
        U, _, Vt = np.linalg.svd(H)
        rotation_matrix = Vt.T @ U.T

        # special reflection case
        if np.linalg.det(rotation_matrix) < 0:
            print("det(R) < R, reflection detected!, correcting for it ...")
            Vt[2,:] *= -1
            rotation_matrix = Vt.T @ U.T

        # center = np.array(self._layer_floating.value.data.shape)/2
        translation_vector = centermass_ref - rotation_matrix @ centermass_float# - (np.eye(3) - rotation_matrix) @ center

        return translation_vector, rotation_matrix



path_to_data = '/home/jvanaret/data/project_egg/spatial_registration'

top=tifffile.imread(f'{path_to_data}/top_small.tif')
bottom=tifffile.imread(f'{path_to_data}/bottom_small.tif')


viewer = napari.Viewer(ndisplay=2)

viewer.add_image(top, name='top', colormap='red', blending='additive')
# viewer.layers[-1].visible = False
viewer.add_image(bottom, name='bottom', colormap='cyan', blending='additive', rendering='attenuated_mip')

viewer.camera.perspective = 24
viewer.grid.enabled = True

viewer.window.add_dock_widget(RegistrationWidget(viewer), area='right')
napari.run()