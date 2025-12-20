import sys
try:
    import MetaTrader5 as mt5
except Exception as e:
    print('ERROR: MetaTrader5 import failed: ' + str(e))
    sys.exit(1)

try:
    if not mt5.initialize():
        print('ERROR: MT5 initialize failed: ' + str(mt5.last_error()))
        sys.exit(1)
    syms = mt5.symbols_get() or []
    names = [getattr(s, 'name', None) or getattr(s, 'symbol', None) for s in syms]
    unique = sorted({x.upper() for x in names if x})
    if not unique:
        print('NO_SYMBOLS_FOUND')
    else:
        for n in unique:
            print(n)
    mt5.shutdown()
except Exception as e:
    print('ERROR: ' + str(e))
    try:
        mt5.shutdown()
    except Exception:
        pass
    sys.exit(1)
