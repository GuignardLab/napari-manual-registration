# :herb: napari-manual-registration

[![License BSD-3](https://img.shields.io/pypi/l/napari-manual-registration.svg?color=green)](https://github.com/jules-vanaret/napari-manual-registration/raw/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/napari-manual-registration.svg?color=green)](https://pypi.org/project/napari-manual-registration)
[![Python Version](https://img.shields.io/pypi/pyversions/napari-manual-registration.svg?color=green)](https://python.org)
[![tests](https://github.com/jules-vanaret/napari-manual-registration/workflows/tests/badge.svg)](https://github.com/jules-vanaret/napari-manual-registration/actions)
[![codecov](https://codecov.io/gh/jules-vanaret/napari-manual-registration/branch/main/graph/badge.svg)](https://codecov.io/gh/jules-vanaret/napari-manual-registration)
[![napari hub](https://img.shields.io/endpoint?url=https://api.napari-hub.org/shields/napari-manual-registration)](https://napari-hub.org/plugins/napari-manual-registration)

<img src="https://github.com/GuignardLab/tapenade/blob/Packaging/imgs/tapenade3.png" width="100">

A plugin to obtain parameters for affine transform used to register two views of the same object, e.g as obtained with dual-view microscopes. 

`napari-manual-registration` is a [napari] plugin that is part of the [Tapenade](https://github.com/GuignardLab/tapenade) project. Tapenade is a tool for the analysis of dense 3D tissues acquired with deep imaging microscopy. It is designed to be user-friendly and to provide a comprehensive analysis of the data.

If you use this plugin for your research, please [cite us](https://github.com/GuignardLab/tapenade/blob/main/README.md#how-to-cite).

## Overview

While working with large and dense 3D and 3D+time gastruloid datasets, we found that being able to visualise and interact with the data dynamically greatly helped processing it.
During the pre-processing stage, dynamical exploration and interaction led to faster tuning of the parameters by allowing direct visual feedback, and gave key biophysical insight during the analysis stage. 

When using our automatic registration tool to spatially register two views of the same organoid, we were sometimes faced with the issue that the tool would not converge to the true registration transformation. This happens when the initial position and orientation of the floating view are too far from their target values. We thus designed a Napari plugin to quickly find a transformation that can be used to initialize our registration tool close to the optimal transformation. From two images loaded in Napari representing two views of the same organoid, the plugin allows the user to 
1. **manually define a rigid transformation** by continually varying 3D rotations and translations while observing the results until a satisfying fit is found
2. **annotate matching salient landmarks** (e.g bright dead cells or lumen-like structures) in both the reference and floating views, from which an optimal rigid transformation can be found automatically using principal component analysis.




## Installation

The plugin obviously requires [napari] to run. If you don't have it yet, follow the instructions [here](https://napari.org/stable/tutorials/fundamentals/installation.html).

The simplest way to install `napari-manual-registration` is via the [napari] plugin manager. Open Napari, go to `Plugins > Install/Uninstall Packages...` and search for `napari-manual-registration`. Click on the install button and you are ready to go!

You can also install `napari-manual-registration` via [pip]:

    pip install napari-manual-registration

To install latest development version :

    pip install git+https://github.com/jules-vanaret/napari-manual-registration.git

## Usage


## Contributing

Contributions are very welcome. Tests can be run with [tox], please ensure
the coverage at least stays the same before you submit a pull request.

## License

Distributed under the terms of the [BSD-3] license,
"napari-manual-registration" is free and open source software

## Issues

If you encounter any problem using this plugin, please [file an issue] on the GitHub repository.

----------------------------------

This [napari] plugin was generated with [Cookiecutter] using [@napari]'s [cookiecutter-napari-plugin] template.

[napari]: https://github.com/napari/napari
[Cookiecutter]: https://github.com/audreyr/cookiecutter
[@napari]: https://github.com/napari
[MIT]: http://opensource.org/licenses/MIT
[BSD-3]: http://opensource.org/licenses/BSD-3-Clause
[GNU GPL v3.0]: http://www.gnu.org/licenses/gpl-3.0.txt
[GNU LGPL v3.0]: http://www.gnu.org/licenses/lgpl-3.0.txt
[Apache Software License 2.0]: http://www.apache.org/licenses/LICENSE-2.0
[Mozilla Public License 2.0]: https://www.mozilla.org/media/MPL/2.0/index.txt
[cookiecutter-napari-plugin]: https://github.com/napari/cookiecutter-napari-plugin

[file an issue]: https://github.com/jules-vanaret/napari-manual-registration/issues

[napari]: https://github.com/napari/napari
[tox]: https://tox.readthedocs.io/en/latest/
[pip]: https://pypi.org/project/pip/
[PyPI]: https://pypi.org/
