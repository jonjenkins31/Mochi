# Mochi Modular Display

Mochi is a modular, extensible framework for creating and displaying animations on a virtual or physical LED matrix. It's designed to be an alternative to commercial products, offering a high degree of customization for developers and hobbyists.

The system is composed of three main components:
*   `mochi_node.py`: The core application that manages animations, handles control commands, and streams frames over ZeroMQ.
*   `mochi_gui.py`: A manual control panel for sending commands to the `mochi_node`.
*   `mochi_vdisplay.py`: A virtual LED display that subscribes to the frame data from the `mochi_node` and renders it on screen.

## Installation

1.  Clone this repository to your local machine.
2.  Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  **Start the Mochi Node:**
    This is the core component that must be running for the GUI and display to function.
    ```bash
    python mochi_node.py
    ```

2.  **Start the Virtual Display:**
    To see the output of the Mochi Node, run the virtual display.
    ```bash
    python mochi_vdisplay.py
    ```

3.  **Start the GUI:**
    For manual control over the animations, colors, and other parameters, launch the GUI.
    ```bash
    python mochi_gui.py
    ```

## Creating Content

### Animations
New animations can be created by adding Python files to the `animations/` directory. Each animation file should contain a class that inherits from a base animation class (or implements a similar interface) and has `frame()` and `render_into()` methods. The `__init__.py` file in the `animations` directory is responsible for discovering and loading these plugins.

### Scripts
For more complex sequences, you can create JSON-based scripts in the `scripts/` directory. These scripts define a timeline of events, such as changing animations, updating colors, or triggering specific events within an animation.
