from src.data.tfl.tfl_client import TflClient
from src.config.config_main import tfl_config


def test_get_modes():
    client = TflClient(tfl_config)
    modes = list(client.get_modes())

    for mode in modes:
        print(mode)

    assert len(modes) > 0
    assert "bus" in modes
    assert "tube" in modes


def test_get_lines_by_mode():
    client = TflClient(tfl_config)
    lines = list(client.get_lines_by_mode(["tube", "bus"]))
    
    assert len(lines) > 0
    
    for line in lines:
        assert "id" in line
        assert "name" in line
        assert "mode" in line
        assert "disruptions" in line
        assert "serviceTypes" in line
        assert isinstance(line["serviceTypes"], list)
        for service_type in line["serviceTypes"]:
            assert isinstance(service_type, str)
