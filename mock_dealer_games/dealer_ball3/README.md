# 20260316 add http request test for pydealerclientLight  

# 20260220 mock dealer for pydealerclientLight for YOLOV8 httpapi BALL3   

Mock Dealer for BALL3 (pydealerclientlight integration test)

How to run:
1) Start model engine HTTP service (the model API) on port 5000.
2) Start this mock dealer (server) so pydealerclientlight can connect:

   python dealer_app_ball3.py

   It listens on 127.0.0.1:2331 by default.

3) Start pydealerclientlight with videolist.xml pointing to gametype="BALL3".

Notes:
- This mock dealer speaks the same TCP binary protocol as the UKBJ21 mock dealer:
  header: !3i (cmd,size,seq)
  login_r: !14s4s
  start/stop predict: !14sh
  predict_result: !14sh + repeated !2hd entries

- UI shows group rows (G0,G1,...) and the values (A,9,10,J,Q,K) with scores.


BALL3 AUTO stop condition:
- stable_times is read from ./videolist.xml attribute stable_times on a <video ...> node (preferred id/name contains 'ball3').
- If missing, default is 5.
