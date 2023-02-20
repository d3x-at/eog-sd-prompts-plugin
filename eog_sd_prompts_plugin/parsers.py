'''logic for getting prompts data out of different image formats'''
import logging
import re
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, NamedTuple
from PIL import Image

# pylint: disable=too-few-public-methods


class PromptData(NamedTuple):
    '''holds prompt information'''
    prompt: str
    negative_prompt: str
    processing_info: List[Tuple[str, str]]
    complete_prompt: str


def get_parameters(eog_image) -> Optional[PromptData]:
    '''try to get sd prompts from the given image'''
    image_file = eog_image.get_file()
    image_info = image_file.query_info('standard::content-type', 0, None)
    mime_type = image_info.get_content_type()
    parameters = None

    if mime_type == "image/png":
        image_path = image_file.get_path()
        try:
            with Image.open(image_path) as image:
                parameters = try_parsers(image)
        except Exception:  # pylint: disable=broad-except
            logging.exception('error while reading %s', image_path)

    return parameters


def try_parsers(image: Image.Image):
    '''loop through available parsers to get image information'''
    for parser in [AUTOMATIC1111Parser]:
        parameters = parser(image).parse()
        if parameters:
            return parameters
    return None


class Parser(ABC):
    '''parser base class'''
    def __init__(self, image: Image.Image):
        self.image = image

    @abstractmethod
    def parse(self) -> Optional[PromptData]:
        '''parse'''


class AUTOMATIC1111Parser(Parser):
    '''parse images created in AUTOMATIC1111's webui'''
    re_param_code = r'\s*([\w ]+):\s*("(?:\\"[^,]|\\"|\\|[^\"])+"|[^,]*)(?:,|$)'
    re_param = re.compile(re_param_code)

    def parse(self):
        if 'parameters' not in self.image.info:
            return None

        lines, processing_info = self._prepare_processing_info(
            self.image.info['parameters'].split("\n"))

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

        return PromptData("\n".join(prompt), "\n".join(negative_prompt),
                          processing_info, self.image.info['parameters'])

    def _prepare_processing_info(self, lines: List[str]) -> Tuple[List[str], List[Tuple[str, str]]]:
        '''attempt to read processing info tags from the parametes lines'''
        parts = self.re_param.findall(lines[-1].strip())
        if len(parts) < 3:
            return lines, []

        return lines[:-1], [(k, v.strip("\"")) for k, v in parts]
