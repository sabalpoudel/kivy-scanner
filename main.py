from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.lang import Builder
from kivy.utils import platform


class MenuScreen(Screen):
    pass


class ScannerScreen(Screen):
    def stop_camera(self):
        s = self.ids.zbarcam
        s.stop()
        print('------------------')
        print(s, self.ids.zbarcam.xcamera.play)
        print('------------------')
        s.xcamera.play = False
        if platform == "android":
            s.xcamera._camera._release_camera()
    pass


class MyApp(App):

    def build(self):
        self.title = 'hello world'
        self.sm = ScreenManager()
        self.sm.add_widget(MenuScreen(name='menu'))
        return self.sm

    def load_screen(self):
        if not self.sm.has_screen('scanner'):
            Builder.load_file('ScannerScreen.kv')
            self.sm.add_widget(ScannerScreen(name='scanner'))
        self.sm.current = 'scanner'

    def remove_scanner_screen(self):
        Builder.unbind_widget('zbarcam')
        Builder.unload_file('ScannerScreen.kv')
        self.sm.remove_widget(ScannerScreen())
        self.sm.current = 'menu'


if __name__ == '__main__':
    MyApp().run()
