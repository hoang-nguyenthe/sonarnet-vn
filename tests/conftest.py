"""Pytest fixtures for the existing standalone smoke-test functions."""
import pytest


@pytest.fixture
def tmp(tmp_path):
    return tmp_path


@pytest.fixture(scope='module')
def smoke_scene_data(tmp_path_factory, request):
    from sonarnet.data.dataset import build_dataset,read_scene_meta,read_ais
    from sonarnet.utils import set_seed
    cfg=request.module._tiny_config(tmp_path_factory.mktemp('smoke-scenes'))
    build_dataset(cfg,set_seed(cfg.seed))
    return cfg,read_scene_meta(cfg.dir_yolo,'test'),read_ais(cfg.dir_yolo,'test')


@pytest.fixture(scope='module')
def cfg(smoke_scene_data):return smoke_scene_data[0]


@pytest.fixture(scope='module')
def meta(smoke_scene_data):return smoke_scene_data[1]


@pytest.fixture(scope='module')
def ais(smoke_scene_data):return smoke_scene_data[2]
