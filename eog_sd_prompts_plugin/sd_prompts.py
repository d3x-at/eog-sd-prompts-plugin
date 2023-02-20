import os
from pathlib import Path
from typing import Optional
from gi.repository import Eog, Gdk, GObject, Gtk

import parsers
from constants import PACKAGE_NAME


PLUGIN_DIR = Path(os.getenv("XDG_DATA_HOME", Path(os.getenv("HOME"), ".local/share")),
                  "eog/plugins", PACKAGE_NAME)

clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)


class SDPromptsPlugin(GObject.Object, Eog.WindowActivatable):
    window = GObject.property(type=Eog.Window)
    parameters: Optional[parsers.PromptData] = None

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
        if image is not None:
            self.set_parameters(image)

    def copy_prompt(self, _) -> None:
        '''copy prompt to clipboard'''
        if self.parameters is not None:
            clipboard.set_text(self.parameters.complete_prompt, -1)

    def set_parameters(self, image):
        parameters = parsers.get_parameters(image)
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

        # positive prompt
        prompt_label = self.ui.get_object("prompt")
        prompt_label.set_label(parameters.prompt)

        # negative prompt
        negative_prompt_label = self.ui.get_object("negative-prompt")
        negative_prompt_label.set_label(parameters.negative_prompt)

        parameters_box = self.ui.get_object("parameters-box")
        # clean up additional parameters
        for child in parameters_box.get_children():
            parameters_box.remove(child)

        # fill parameters box with new items
        for key, value in parameters.processing_info:
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
            parameters_box.add(hbox)
            hbox.add(Gtk.Label(
                f'{key}:', xalign=0, sensitive=False, selectable=True))
            hbox.add(Gtk.Label(value, xalign=0, selectable=True))

        parameters_box.show_all()
