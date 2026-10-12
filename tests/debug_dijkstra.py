import sys, heapq, math
from datetime import datetime, timedelta
from app.services.routing_engine import RoutingEngine

re = RoutingEngine()

from_stop = re.resolve_stop('Nemocnica Šaca')
to_stop = re.resolve_stop('Fábryho')
from_canonical = re.get_canonical_name(from_stop)
to_canonical = re.get_canonical_name(to_stop)

target_platforms = re.stops_by_canonical_name.get(to_canonical, [to_stop])
target_ids = set()
for tp in target_platforms:
    target_ids.add(tp["stop_id"])
    target_ids.add(str(tp["stop_id"]))
    try:
        target_ids.add(int(str(tp["stop_id"]).split("_")[0]))
    except ValueError:
        pass
    if tp.get("parent_stop_id") is not None:
        target_ids.add(tp["parent_stop_id"])
        target_ids.add(str(tp["parent_stop_id"]))

print("Target IDs:", target_ids, flush=True)

start_platforms = re.stops_by_canonical_name.get(from_canonical, [from_stop])
counter = 0
pq = []
for sp in start_platforms:
    counter += 1
    heapq.heappush(pq, (0, counter, sp["stop_id"], None, []))

visited = {}
wait_cache = {}
dep_dt = datetime.now()

pop_count = 0
while pq and pop_count < 25000:
    cost_sec, _, u, mode, path = heapq.heappop(pq)
    pop_count += 1

    if pop_count % 2000 == 0:
        print(f"[{pop_count}] pq_len={len(pq)} cost={cost_sec} u={u} mode={mode} path_len={len(path)} visited_len={len(visited)}", flush=True)

    state_key = (u, mode)
    if state_key in visited and visited[state_key] <= cost_sec:
        continue
    visited[state_key] = cost_sec

    if u in target_ids:
        print(f"FOUND TARGET at pop {pop_count}! cost={cost_sec}", flush=True)
        break

    if u not in re.stops_by_id:
        continue
    u_stop = re.stops_by_id[u]
    u_lat = u_stop.get("latitude")
    u_lon = u_stop.get("longitude")
    if u_lat is None or u_lon is None:
        continue

    # 1. Walk
    for w in re.adjacency_list.get(u, []):
        v = w["to_stop_id"]
        if v not in re.stops_by_id:
            continue
        w_sec = w["walk_time_seconds"]
        is_platform_transfer = (w_sec == 0 or w.get("is_platform_transfer", False))
        if (mode and mode.startswith("walk")) and not is_platform_transfer:
            continue
        counter += 1
        next_mode = mode if is_platform_transfer else "walk"
        heapq.heappush(pq, (cost_sec + w_sec, counter, v, next_mode, path + [1]))

    # 2. Transit
    current_node_dt = dep_dt + timedelta(seconds=cost_sec)
    u_lines = u_stop.get("lines", [])
    for line in u_lines:
        cand_stops = re.lines_to_stops.get(line, [])
        wait_key = (u, line)
        if wait_key not in wait_cache:
            wait_cache[wait_key] = re.calculate_transit_edge_wait(u, line, current_node_dt, allow_network=False)
        wait_info = wait_cache[wait_key]
        wait_sec = wait_info["wait_seconds"]

        for v in cand_stops:
            if v == u or v not in re.stops_by_id:
                continue
            v_stop = re.stops_by_id[v]
            v_lat = v_stop.get("latitude")
            v_lon = v_stop.get("longitude")
            if v_lat is None or v_lon is None:
                continue
            dx = (v_lon - u_lon) * 73400.0
            dy = (v_lat - u_lat) * 111200.0
            d2 = dx * dx + dy * dy
            if d2 > 144000000:
                continue
            dist_m = math.sqrt(d2)
            ride_sec = max(75, int(dist_m * 0.1923))
            transfer_penalty = 120 if mode and mode != f"transit_{line}" else 0
            total_step_sec = wait_sec + ride_sec + transfer_penalty

            v_state = (v, f"transit_{line}")
            if v_state in visited and visited[v_state] <= cost_sec + total_step_sec:
                continue
            counter += 1
            heapq.heappush(pq, (cost_sec + total_step_sec, counter, v, f"transit_{line}", path + [1]))

print(f"Done loop! pop_count={pop_count}, pq_len={len(pq)}", flush=True)
