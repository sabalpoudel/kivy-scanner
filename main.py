from kivy.app import App
from kivy.lang import Builder
from kivy.utils import platform
from kivy.uix.screenmanager import ScreenManager, Screen

import PIL
from PIL import ImageOps
from kivy.clock import Clock
from kivy.logger import Logger
from collections import namedtuple
from kivy.properties import ListProperty, NumericProperty


def is_android():
    return platform == 'android'


def is_ios():
    return platform == 'ios'


def fix_android_image(pil_image):
    """
    On Android, the image seems mirrored and rotated somehow, refs #32.
    """
    if not is_android():
        return pil_image
    pil_image = pil_image.rotate(90)
    pil_image = ImageOps.mirror(pil_image)
    return pil_image


class ZBarDecoder:
    @classmethod
    def is_usable(cls):
        return False

    def validate_code_types(self, code_types):
        available_code_types = self.get_available_code_types()

        if not all(
            code_type in available_code_types
            for code_type in code_types
        ):
            raise ValueError(
                f'Invalid code types: {code_types}. '
                f'Available code types: {available_code_types}'
            )


class PyZBarDecoder(ZBarDecoder):
    @classmethod
    def is_usable(cls):
        try:
            from pyzbar import pyzbar
            cls.pyzbar = pyzbar
            return True

        except ImportError:
            return False

    def get_available_code_types(self):
        return set(self.pyzbar.ZBarSymbol.__members__.keys())

    def decode(self, image, code_types):
        self.validate_code_types(code_types)
        pyzbar_code_types = set(
            getattr(self.pyzbar.ZBarSymbol, code_type)
            for code_type in code_types
        )
        return [
            ScannerScreen2.Symbol(type=code.type, data=code.data)
            for code in self.pyzbar.decode(
                image,
                symbols=pyzbar_code_types,
            )
        ]


class ZBarLightDecoder(ZBarDecoder):
    @classmethod
    def is_usable(cls):
        try:
            import zbarlight
            cls.zbarlight = zbarlight
            return True

        except ImportError:
            return False

    def get_available_code_types(self):
        return set(self.zbarlight.Symbologies.keys())

    def decode(self, image, code_types):
        self.validate_code_types(code_types)
        zbarlight_code_types = set(
            code_type.lower()
            for code_type in code_types
        )
        codes = self.zbarlight.scan_codes(
            zbarlight_code_types,
            image
        )

        # zbarlight.scan_codes() returns None instead of []
        if not codes:
            return []

        return [
            ScannerScreen2.Symbol(type=None, data=code)
            for code in codes
        ]


class XZbarDecoder(ZBarDecoder):
    """Proxy-like that deals with all the implementations."""
    available_implementations = {
        'pyzbar': PyZBarDecoder,
        'zbarlight': ZBarLightDecoder,
    }
    zbar_decoder = None

    def __init__(self):
        # making it a singleton so it gets initialized once
        XZbarDecoder.zbar_decoder = (
            self.zbar_decoder or self._get_implementation())

    def _get_implementation(self):
        for name, implementation in self.available_implementations.items():
            if implementation.is_usable():
                zbar_decoder = implementation()
                Logger.info('ScannerScreen2: Using implementation %s', name)
                return zbar_decoder
        else:
            raise ImportError(
                'No zbar implementation available '
                f'(tried {", ".join(self.available_implementations.keys())})'
            )

    def get_available_code_types(self):
        return self.zbar_decoder.get_available_code_types()

    def decode(self, image, code_types):
        return self.zbar_decoder.decode(image, code_types)


class MenuScreen(Screen):
    pass


class CameraScreen(Screen):
    cam_no = NumericProperty(0)
    resolution = ListProperty([640, 480])

    symbols = ListProperty([])
    Symbol = namedtuple('Symbol', ['type', 'data'])
    # checking all possible types by default
    code_types = ListProperty(XZbarDecoder().get_available_code_types())

    def on_pre_enter(self):
        self.ids.cam.play = True
        # open if camera is closed
        if not self.ids.cam._camera._device.isOpened():
            self.ids.cam._camera._device.open(0)
        self.ids.cam.texture = self.ids.cam._camera.texture

    def on_enter(self):
        self.ids.cam._camera.bind(on_texture=self._on_texture)

    def _on_texture(self, instance):
        self.symbols = self._detect_qrcode_frame(
            texture=instance.texture, code_types=self.code_types)

    @classmethod
    def _detect_qrcode_frame(cls, texture, code_types):
        image_data = texture.pixels
        size = texture.size
        # Fix for mode mismatch between texture.colorfmt and data returned by
        # texture.pixels. texture.pixels always returns RGBA, so that should
        # be passed to PIL no matter what texture.colorfmt returns. refs:
        # https://github.com/AndreMiras/garden.zbarcam/issues/41
        pil_image = PIL.Image.frombytes(mode='RGBA', size=size,
                                        data=image_data)
        pil_image = fix_android_image(pil_image)
        return XZbarDecoder().decode(pil_image, code_types)

    def on_leave(self):
        self.ids.cam.play = False
        self.ids.cam.texture = None
        self.ids.cam._camera._device.release()

    pass


class ScannerScreen2(Screen):
    camera_index = NumericProperty(0)
    resolution = ListProperty([640, 480])

    symbols = ListProperty([])
    Symbol = namedtuple('Symbol', ['type', 'data'])
    # checking all possible types by default
    code_types = ListProperty(XZbarDecoder().get_available_code_types())
    kv_loaded = False

    def on_pre_enter(self):
        Clock.schedule_once(lambda dt: self._setup())

    def _setup(self):
        self.ids.xCam.bind(on_camera_ready=self._on_camera_ready)
        # camera may still be ready before we bind the event
        if self.ids.xCam._camera is not None:
            self._on_camera_ready(self.ids.xCam)

    def _on_camera_ready(self, xcamera):
        xcamera.play = True
        # open if camera is closed
        if not xcamera._camera._device.isOpened():
            xcamera._camera._device.open(0)
        xcamera.texture = xcamera._camera.texture
        xcamera._camera.bind(on_texture=self._on_texture)

    def _on_texture(self, instance):
        self.symbols = self._detect_qrcode_frame(
            texture=instance.texture, code_types=self.code_types)

    @classmethod
    def _detect_qrcode_frame(cls, texture, code_types):
        image_data = texture.pixels
        size = texture.size
        # Fix for mode mismatch between texture.colorfmt and data returned by
        # texture.pixels. texture.pixels always returns RGBA, so that should
        # be passed to PIL no matter what texture.colorfmt returns. refs:
        # https://github.com/AndreMiras/garden.zbarcam/issues/41
        pil_image = PIL.Image.frombytes(mode='RGBA', size=size,
                                        data=image_data)
        pil_image = fix_android_image(pil_image)
        return XZbarDecoder().decode(pil_image, code_types)

    def on_leave(self):
        self.ids.xCam.play = False
        self.ids.xCam.texture = None
        self.ids.xCam._camera._device.release()
    pass


class MyApp(App):

    def build(self):
        self.title = 'hello world'
        self.sm = ScreenManager()
        self.sm.add_widget(MenuScreen(name='menu'))
        return self.sm

    def load_screen(self, name):
        if name == 'scanner2':
            if not self.sm.has_screen('scanner2'):
                Builder.load_file('Scanner2.kv')
                self.sm.add_widget(ScannerScreen2(name='scanner2'))
            self.go_to_screen('scanner2')
        elif name == 'camera':
            if not self.sm.has_screen('camera'):
                Builder.load_file('Camera.kv')
                self.sm.add_widget(CameraScreen(name='camera'))
            self.go_to_screen('camera')
        pass

    def go_to_screen(self, screen):
        self.sm.current = screen


if __name__ == '__main__':
    MyApp().run()
