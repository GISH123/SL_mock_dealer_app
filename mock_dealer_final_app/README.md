# mock_dealer_app

Project layout:
- `dealer_app_ball3/` - released BALL3 mock dealer code and its `.spec` files
- `dealer_app_bac/` - BAC wsstyle mock dealer code
- `card_shown_ui/` - shared card image assets used by both apps
- `requirements.txt` - shared Python dependencies
- `version.txt` - BALL3 TCP build version source
- `versionhttp.txt` - BALL3 HTTP build version source

## Run

BALL3 TCP:
```bash
python dealer_app_ball3/dealer_app_ball3.py
```

BALL3 HTTP:
```bash
python dealer_app_ball3/dealer_app_ball3_http.py
```

BAC wsstyle:
```bash
python dealer_app_bac/main.py
```

## Build

BALL3 TCP spec:
- `dealer_app_ball3/MockDealerBALL3.spec`

BALL3 HTTP spec:
- `dealer_app_ball3/MockDealerBALL3http_v2.spec`

The BALL3 specs now read `version.txt` / `versionhttp.txt` and `card_shown_ui/` from the project root, while the spec files themselves live inside `dealer_app_ball3/`.


## Reorganized structure
- dealer_BAC/: BAC launcher + GUI + spec
- dealer_ball3/: BALL3 TCP / HTTP mock dealer + specs
- card_shown_ui/: runtime UI assets (add manually before packaging)
- shared_runtime.py / shared_build_utils.py: shared helpers used by both dealers
