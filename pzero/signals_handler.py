
# This function disconnect all the signals of a QObject
def disconnect_all_signals(signals):
    # print("start disconnect_all_signals")
    # for each signal inside the list, disconnect it
    for signal in signals:
        # print(signal)
        signal.disconnect()

    # print("end disconnect_all_signals")

    return

