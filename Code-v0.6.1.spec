# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\Admin\\Desktop\\api中转站\\code\\launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\Admin\\Desktop\\api中转站\\code\\VERSION', '.'), ('C:\\Users\\Admin\\Desktop\\api中转站\\code\\app.js', '.'), ('C:\\Users\\Admin\\Desktop\\api中转站\\code\\agent-runtime.js', '.'), ('C:\\Users\\Admin\\Desktop\\api中转站\\code\\src', 'src'), ('C:\\Users\\Admin\\Desktop\\api中转站\\code\\index.html', '.'), ('C:\\Users\\Admin\\Desktop\\api中转站\\code\\dist\\frontend\\code.bundle.js', 'dist/frontend'), ('C:\\Users\\Admin\\Desktop\\api中转站\\code\\dist\\frontend\\index.classic.html', 'dist/frontend'), ('C:\\Users\\Admin\\Desktop\\api中转站\\code\\styles.css', '.'), ('C:\\Users\\Admin\\Desktop\\api中转站\\code\\code-icon.ico', '.'), ('C:\\Users\\Admin\\Desktop\\api中转站\\code\\code-icon.png', '.'), ('C:\\Users\\Admin\\Desktop\\api中转站\\code\\assets', 'assets'), ('C:\\Users\\Admin\\Desktop\\api中转站\\code\\data\\skills', 'data/skills'), ('C:\\Users\\Admin\\Desktop\\api中转站\\code\\data\\memory', 'data/memory')],
    hiddenimports=['json', 'mimetypes', 'pystray', 'PIL.Image', 'PIL.BmpImagePlugin', 'PIL.IcoImagePlugin', 'PIL.PngImagePlugin'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PIL.ImageQt', 'PIL.ImageDraw2', 'PIL.ImageFont', 'PIL.ImageFilter', 'PIL.ImageEnhance', 'PIL.ImageMath', 'PIL.ImageMorph', 'PIL.ImageOps', 'PIL.ImagePath', 'PIL.ImageStat', 'PIL.ImageTransform', 'PIL.ImageWin', 'PIL.ImImagePlugin', 'PIL.BlpImagePlugin', 'PIL.BufrStubImagePlugin', 'PIL.CurImagePlugin', 'PIL.DcxImagePlugin', 'PIL.DdsImagePlugin', 'PIL.EpsImagePlugin', 'PIL.FitsImagePlugin', 'PIL.FliImagePlugin', 'PIL.FpxImagePlugin', 'PIL.FtexImagePlugin', 'PIL.GbrImagePlugin', 'PIL.GdImageFile', 'PIL.GifImagePlugin', 'PIL.GribStubImagePlugin', 'PIL.Hdf5StubImagePlugin', 'PIL.IcnsImagePlugin', 'PIL.ImImagePlugin', 'PIL.ImtImagePlugin', 'PIL.IptcImagePlugin', 'PIL.Jpeg2KImagePlugin', 'PIL.JpegImagePlugin', 'PIL.McIdasImagePlugin', 'PIL.MicImagePlugin', 'PIL.MpegImagePlugin', 'PIL.MpoImagePlugin', 'PIL.MspImagePlugin', 'PIL.PalmImagePlugin', 'PIL.PcdImagePlugin', 'PIL.PcxImagePlugin', 'PIL.PdfImagePlugin', 'PIL.PixarImagePlugin', 'PIL.PpmImagePlugin', 'PIL.PsdImagePlugin', 'PIL.SgiImagePlugin', 'PIL.SpiderImagePlugin', 'PIL.SunImagePlugin', 'PIL.TgaImagePlugin', 'PIL.TiffImagePlugin', 'PIL.WebPImagePlugin', 'PIL.WmfImagePlugin', 'PIL.XbmImagePlugin', 'PIL.XpmImagePlugin', 'PIL.XVThumbImagePlugin'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Code-v0.6.1',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='C:\\Users\\Admin\\Desktop\\api中转站\\code\\file_version_info.txt',
    icon=['C:\\Users\\Admin\\Desktop\\api中转站\\code\\code-icon.ico'],
)
