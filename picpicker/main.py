#!/usr/bin/env python3
"""皮卡比 PicPicker 主程序"""

import sys
from picpicker.gui import PicPickerApp

def main() -> None:
    app = PicPickerApp()
    app.run()


if __name__ == "__main__":
    main()
