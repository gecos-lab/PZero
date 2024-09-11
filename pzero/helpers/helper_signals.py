"""helper_signals.py
PZero© Andrea Bistacchi"""


def disconnect_all_signals(signals):
    """This function disconnects all signals of a QObject"""
    for signal in signals:
        # for each signal inside the list, disconnect it
        signal.disconnect()
    return
