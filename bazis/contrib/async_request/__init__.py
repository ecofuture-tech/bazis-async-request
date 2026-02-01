try:
    from importlib.metadata import PackageNotFoundError, version
    __version__ = version('bazis-async-request')
except PackageNotFoundError:
    __version__ = 'dev'
