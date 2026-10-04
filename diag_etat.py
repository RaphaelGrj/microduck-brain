import truth
from poc_robotd_client import RobotdClient, SOCK_PATH
c = RobotdClient(SOCK_PATH)
c.request("robot.subscribe", {})
s = c.read_state_frame()
d = truth.read()["ducks"][0]
print("policy", s["policy"], "| fallen", s["safety"]["fallen"], "| limp", s["safety"]["limp"],
      "| tronc z (verite)", round(d["pos"][2], 3), "| quat", [round(v, 2) for v in d["quat"]])
