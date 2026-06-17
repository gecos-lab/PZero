def pytest_addoption(parser):
    parser.addoption(
        "--dat-file",
        action="store",
        default=None,
        help="Path to a .dat point cloud file (x y z per row) for the real-data test",
    )
