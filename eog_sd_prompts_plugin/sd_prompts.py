import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple
from gi.repository import Eog, Gdk, GObject, Gtk
from PIL import Image

from constants import PACKAGE_NAME

PLUGIN_DIR = Path(os.getenv("XDG_DATA_HOME", Path(os.getenv("HOME"), ".local/share")),
                  "eog/plugins", PACKAGE_NAME)

re_param_code = r'\s*([\w ]+):\s*("(?:\\"[^,]|\\"|\\|[^\"])+"|[^,]*)(?:,|$)'
re_param = re.compile(re_param_code)

clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)


class SDPromptsPlugin(GObject.Object, Eog.WindowActivatable):
    window = GObject.property(type=Eog.Window)
    parameters: Optional[str] = None

    def __init__(self):
        self.ui = Gtk.Builder()
        self.ui.add_from_file(str(PLUGIN_DIR / "sd_prompts.glade"))

        self.info_label = self.ui.get_object("info-label")
        self.prompts_container = self.ui.get_object("prompts-container")

        button_copy_prompt = self.ui.get_object("copy-prompt-button")
        button_copy_prompt.connect("clicked", self.copy_prompt)

    def do_activate(self) -> None:
        # initialize Gtk Components
        self.sidebar = self.ui.get_object("sd-prompts-root")
        if self.sidebar is None:
            return

        # connect to EOG's image notifications
        self.image_loaded_id = self.window.get_view().connect(
            "notify::image", self.notify_image_cb)

        # add as a new sidebar
        self.window.get_sidebar().add_page("SD Prompt", self.sidebar)

        # try to display our new sidebar
        self.window.get_sidebar().set_page(self.sidebar)

    def do_deactivate(self) -> None:
        if self.sidebar is not None:
            # Disconnect image notify callback
            self.window.get_view().disconnect(self.image_loaded_id)
            # remove our sidebar
            self.window.get_sidebar().remove_page(self.sidebar)

    def notify_image_cb(self, *_) -> None:
        '''handle image notifications'''
        image = self.window.get_image()
        if image is None:
            return

        parameters = None
        image_file = image.get_file()
        image_info = image_file.query_info('standard::content-type', 0, None)
        mime_type = image_info.get_content_type()

        if mime_type == "image/png":
            image_path = image_file.get_path()
            try:
                with Image.open(image_path) as image:
                    parameters = image.info['parameters'] if 'parameters' in image.info else None
            except:
                logging.exception(f'error while opening {image_path}')

        self.set_parameters(parameters)

    def copy_prompt(self, _) -> None:
        '''copy prompt to clipboard'''
        if self.parameters is not None:
            clipboard.set_text(self.parameters, -1)

    def set_parameters(self, parameters: Optional[str]):
        self.parameters = parameters

        if parameters is None:
            if not self.info_label.is_visible():
                self.info_label.set_label("no prompt found")
                self.info_label.set_visible(True)
                self.prompts_container.set_visible(False)
            return

        if self.info_label.is_visible():
            self.info_label.set_visible(False)
            self.prompts_container.set_visible(True)

        prompt, negative_prompt, processing_info = parse_parameters(parameters)

        # positive prompt
        prompt_label = self.ui.get_object("prompt")
        prompt_label.set_label(prompt)

        # negative prompt
        negative_prompt_label = self.ui.get_object("negative-prompt")
        negative_prompt_label.set_label(negative_prompt)

        parameters_box = self.ui.get_object("parameters-box")
        # clean up additional parameters
        for child in parameters_box.get_children():
            parameters_box.remove(child)

        # fill parameters box with new items
        for key, value in processing_info:
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
            parameters_box.add(hbox)
            hbox.add(Gtk.Label(
                f'{key}:', xalign=0, sensitive=False, selectable=True))
            hbox.add(Gtk.Label(value, xalign=0, selectable=True))

        parameters_box.show_all()


def parse_parameters(parameters: str) -> Tuple[str, str, List[Tuple[str, str]]]:
    lines, processing_info = parse_processing_info(parameters.split("\n"))
    prompt, negative_prompt = [], []
    i = 0

    # prompt
    for line in lines:
        line = line.strip()
        if line.startswith("Negative prompt:"):
            line = line[16:]
            break
        prompt.append(line)
        i += 1

    # negative prompt
    for line in lines[i:]:
        negative_prompt.append(line.strip())

    return "\n".join(prompt), "\n".join(negative_prompt), processing_info


def parse_processing_info(lines: List[str]) -> Tuple[List[str], List[Tuple[str, str]]]:
    '''attempt to read processing info tags from the parametes lines'''
    parts = re_param.findall(lines[-1].strip())
    if len(parts) < 3:
        return lines, []

    return lines[:-1], [(k, v.strip("\"")) for k, v in parts]
