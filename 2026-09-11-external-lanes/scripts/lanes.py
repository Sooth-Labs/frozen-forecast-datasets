import re
EXCL_PREFIX=("panel_sooth_","panel_rp_ensemble","panel_openharness","panel_v11_","panel_v21_","panel_reflector_","panel_ormolu","panel_meta","panel_summarizer")
EXCL_EXACT={"panel_dromedary_imitation_1"}
def keep(lane): return not (lane.startswith(EXCL_PREFIX) or lane in EXCL_EXACT)
def base(lane): return re.sub(r"_t\d+_[a-z]+$","",lane[len("panel_"):])
