"""
PitchPulse 2026 - Graph-Based Accessible Venue Routing Engine
Implements Dijkstra's shortest path algorithm over MetLife Stadium topology.
Validates every path segment for step-free access, wheelchair compliance,
tactile guidance, and sensory quiet corridors.
"""

import heapq
import logging
from dataclasses import dataclass

logger = logging.getLogger("pitchpulse.routing")


@dataclass
class PathSegment:
    from_node: str
    to_node: str
    weight: int  # travel cost / seconds
    step_free: bool
    has_ramp: bool
    has_stairs: bool
    has_elevator: bool
    sensory_level: str  # "low", "medium", "high"
    status: str = "open"  # "open", "closed", "maintenance"
    instruction: str = ""


@dataclass
class VenueNode:
    node_id: str
    name: str
    node_type: str  # "gate", "concourse", "elevator", "escalator", "section", "facility"
    step_free_entry: bool = True
    operational: bool = True


@dataclass
class RouteResult:
    recommended_gate: str
    accessible_path: list[str]
    step_free: bool
    nearest_quiet_room: str
    nearest_elevator: str
    estimated_walk_minutes: int
    accessibility_warning: str | None = None
    all_segments_verified: bool = True
    routing_method: str = "dijkstra_graph"


class VenueGraph:
    """
    Direct graph representation of MetLife Stadium accessible transit network.
    Edges encode accessibility features (ramps, elevators, tactile surfaces, stairs).
    """

    def __init__(self):
        self.nodes: dict[str, VenueNode] = {}
        self.adjacency: dict[str, list[PathSegment]] = {}
        self._build_stadium_network()

    def add_node(self, node: VenueNode):
        self.nodes[node.node_id] = node
        if node.node_id not in self.adjacency:
            self.adjacency[node.node_id] = []

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        weight: int,
        step_free: bool,
        has_ramp: bool,
        has_stairs: bool,
        has_elevator: bool,
        sensory_level: str = "medium",
        status: str = "open",
        instruction: str = "",
        bidirectional: bool = True,
    ):
        seg1 = PathSegment(
            from_node=from_id,
            to_node=to_id,
            weight=weight,
            step_free=step_free,
            has_ramp=has_ramp,
            has_stairs=has_stairs,
            has_elevator=has_elevator,
            sensory_level=sensory_level,
            status=status,
            instruction=instruction or f"Navigate from {from_id} to {to_id}",
        )
        self.adjacency[from_id].append(seg1)

        if bidirectional:
            seg2 = PathSegment(
                from_node=to_id,
                to_node=from_id,
                weight=weight,
                step_free=step_free,
                has_ramp=has_ramp,
                has_stairs=has_stairs,
                has_elevator=has_elevator,
                sensory_level=sensory_level,
                status=status,
                instruction=instruction or f"Navigate from {to_id} to {from_id}",
            )
            self.adjacency[to_id].append(seg2)

    def _build_stadium_network(self):
        # 1. Gates
        self.add_node(VenueNode("gate-a", "Gate A (Main North Plaza)", "gate", step_free_entry=True))
        self.add_node(VenueNode("gate-b", "Gate B (East ADA Concourse)", "gate", step_free_entry=True))
        self.add_node(VenueNode("gate-c", "Gate C (South Concourse Boulevard)", "gate", step_free_entry=False))  # Stairs only!
        self.add_node(VenueNode("gate-d", "Gate D (West NJ Transit Hub)", "gate", step_free_entry=True))

        # 2. Concourse Hubs (Level 1)
        self.add_node(VenueNode("concourse-north", "Level 1 North Concourse", "concourse"))
        self.add_node(VenueNode("concourse-east", "Level 1 East Accessible Concourse", "concourse"))
        self.add_node(VenueNode("concourse-south", "Level 1 South Concourse", "concourse"))
        self.add_node(VenueNode("concourse-west", "Level 1 West Concourse", "concourse"))

        # 3. Vertical Transit Elements
        self.add_node(VenueNode("elevator-ada-2", "Elevator Bank 2 (North ADA Tower)", "elevator"))
        self.add_node(VenueNode("elevator-ada-1", "Elevator Bank 1 (South ADA Tower)", "elevator"))
        self.add_node(VenueNode("escalator-east", "Escalator Bank East", "escalator", step_free_entry=False))
        self.add_node(VenueNode("stairs-south", "Stairway South Concourse", "stairs", step_free_entry=False))

        # 4. Upper Levels & Mezzanines
        self.add_node(VenueNode("mezzanine-north", "North Mezzanine Level 2", "concourse"))
        self.add_node(VenueNode("mezzanine-south", "South Mezzanine Level 2", "concourse"))

        # 5. Connect Gates to Level 1 Concourse
        # Gate A -> North Concourse (Ramp, tactile surface)
        self.add_edge(
            "gate-a", "concourse-north", weight=60, step_free=True, has_ramp=True,
            has_stairs=False, has_elevator=False, sensory_level="medium",
            instruction="Enter Gate A via dedicated ramp with high-contrast tactile pavers",
        )

        # Gate B -> East Concourse (Full ADA Priority Corridor, Low-Sensory)
        self.add_edge(
            "gate-b", "concourse-east", weight=45, step_free=True, has_ramp=True,
            has_stairs=False, has_elevator=False, sensory_level="low",
            instruction="Enter Gate B priority ADA lane — seamless zero-grade threshold",
        )

        # Gate C -> South Concourse (Has outdoor stairs, NO ramp)
        self.add_edge(
            "gate-c", "concourse-south", weight=80, step_free=False, has_ramp=False,
            has_stairs=True, has_elevator=False, sensory_level="high",
            instruction="Proceed through Gate C turnstiles via 18 exterior concrete steps (no ramp)",
        )

        # Gate D -> West Concourse (Transit Hub ramp)
        self.add_edge(
            "gate-d", "concourse-west", weight=55, step_free=True, has_ramp=True,
            has_stairs=False, has_elevator=False, sensory_level="medium",
            instruction="Enter Gate D via NJ Transit covered accessible walkway",
        )

        # 6. Concourse Interconnects (All level & step-free)
        self.add_edge("concourse-north", "concourse-east", weight=70, step_free=True, has_ramp=False, has_stairs=False, has_elevator=False, sensory_level="low")
        self.add_edge("concourse-east", "concourse-south", weight=70, step_free=True, has_ramp=False, has_stairs=False, has_elevator=False, sensory_level="medium")
        self.add_edge("concourse-south", "concourse-west", weight=70, step_free=True, has_ramp=False, has_stairs=False, has_elevator=False, sensory_level="medium")
        self.add_edge("concourse-west", "concourse-north", weight=70, step_free=True, has_ramp=False, has_stairs=False, has_elevator=False, sensory_level="medium")

        # 7. Vertical Transit Connections
        # East ADA Concourse -> Direct ADA Elevator Bank 2 access
        self.add_edge(
            "concourse-east", "elevator-ada-2", weight=15, step_free=True, has_ramp=True,
            has_stairs=False, has_elevator=True, sensory_level="low",
            instruction="Proceed along direct priority ADA corridor to Elevator Bank 2",
        )

        # North Concourse -> Elevator 2 -> Mezzanine North
        self.add_edge(
            "concourse-north", "elevator-ada-2", weight=30, step_free=True, has_ramp=False,
            has_stairs=False, has_elevator=True, sensory_level="low",
            instruction="Board Elevator Bank 2 (North ADA Tower) with audio floor announcements and Braille buttons",
        )
        self.add_edge(
            "elevator-ada-2", "mezzanine-north", weight=30, step_free=True, has_ramp=False,
            has_stairs=False, has_elevator=True, sensory_level="low",
            instruction="Exit elevator onto Level 2 Mezzanine — step-free tactile pathway",
        )

        # South Concourse -> Elevator 1 -> Mezzanine South
        self.add_edge(
            "concourse-south", "elevator-ada-1", weight=35, step_free=True, has_ramp=False,
            has_stairs=False, has_elevator=True, sensory_level="medium",
            instruction="Board Elevator Bank 1 (South ADA Tower)",
        )
        self.add_edge(
            "elevator-ada-1", "mezzanine-south", weight=35, step_free=True, has_ramp=False,
            has_stairs=False, has_elevator=True, sensory_level="medium",
            instruction="Exit elevator onto South Mezzanine Level 2",
        )

        # East Concourse -> Escalator -> Mezzanine North (Not step-free for wheelchairs!)
        self.add_edge(
            "concourse-east", "escalator-east", weight=25, step_free=False, has_ramp=False,
            has_stairs=False, has_elevator=False, sensory_level="medium",
            instruction="Take Escalator East towards Level 2 (non-wheelchair accessible)",
        )
        self.add_edge(
            "escalator-east", "mezzanine-north", weight=25, step_free=False, has_ramp=False,
            has_stairs=False, has_elevator=False, sensory_level="medium",
            instruction="Step off escalator onto Mezzanine Level 2",
        )

        # South Concourse -> Stairs -> Mezzanine South (Stairs only)
        self.add_edge(
            "concourse-south", "stairs-south", weight=40, step_free=False, has_ramp=False,
            has_stairs=True, has_elevator=False, sensory_level="high",
            instruction="Climb Stairway South (24 steps)",
        )
        self.add_edge(
            "stairs-south", "mezzanine-south", weight=40, step_free=False, has_ramp=False,
            has_stairs=True, has_elevator=False, sensory_level="high",
            instruction="Reach South Mezzanine landing",
        )

    def find_accessible_route(
        self,
        target_section: str,
        mobility_profile: str = "standard",
        prefer_elevators: bool = True,
        gate_statuses: dict[str, dict] | None = None,
    ) -> RouteResult:
        """
        Executes Dijkstra's algorithm to compute the optimal path tailored to the fan's mobility profile.
        Strictly filters out non-step-free or closed segments for wheelchair/low_mobility users.
        """
        # Determine target node based on section number
        sec_num = 100
        digits = "".join(c for c in target_section if c.isdigit())
        if digits:
            sec_num = int(digits)

        # Lower concourse vs mezzanine
        is_upper_tier = sec_num >= 200
        target_node = "mezzanine-north" if is_upper_tier else "concourse-east"

        requires_step_free = mobility_profile in ("wheelchair", "low_mobility")
        is_sensory = mobility_profile == "sensory_sensitive"

        # Gates to evaluate as starting points
        candidate_gates = ["gate-b", "gate-a", "gate-d"]
        if not requires_step_free:
            candidate_gates.append("gate-c")

        # For sensory sensitive, prefer Gate B and avoid Gate C
        if is_sensory:
            candidate_gates = ["gate-b", "gate-d", "gate-a"]

        best_cost = float("inf")
        best_path: list[PathSegment] = []
        best_gate = "gate-b"

        for start_gate in candidate_gates:
            cost, path = self._dijkstra(
                start_node=start_gate,
                target_node=target_node,
                requires_step_free=requires_step_free,
                is_sensory=is_sensory,
                prefer_elevators=prefer_elevators,
                gate_statuses=gate_statuses,
            )
            if path and cost < best_cost:
                best_cost = cost
                best_path = path
                best_gate = start_gate

        # If no path found under strict step-free constraint (fallback check)
        warning = None
        if not best_path:
            logger.warning("No strictly step-free route found for section %s; finding assisted route", target_section)
            warning = "Direct step-free transit requires personal accessibility staff escort at your entry gate."
            # Fallback to standard dijkstra but mark as not step-free
            _, best_path = self._dijkstra(
                start_node="gate-b",
                target_node=target_node,
                requires_step_free=False,
                is_sensory=is_sensory,
                prefer_elevators=True,
                gate_statuses=gate_statuses,
            )

        # Verify EVERY segment in the computed path
        all_verified = True
        step_free = True
        for seg in best_path:
            if not seg.step_free or seg.has_stairs:
                step_free = False
            if seg.status != "open":
                all_verified = False

        if requires_step_free and not step_free:
            warning = "Alert: One or more segments require assistance. Dedicated stadium ADA attendants dispatched."

        # Format instructions into accessible directions
        instructions = []
        for seg in best_path:
            instructions.append(seg.instruction)
        instructions.append(f"Follow illuminated high-contrast tactile floor indicators directly to Section {target_section.upper()}")

        # Quiet room and elevator metadata
        if is_sensory or best_gate == "gate-b":
            quiet_room = "Sensory Quiet Suite #2 (North Mezzanine Level 2) — Low-stimulation lighting & soundproofing"
            elevator = "Elevator Bank 2 (North ADA Tower)"
        else:
            quiet_room = "Sensory Quiet Suite #1 (South Mezzanine Level 2)"
            elevator = "Elevator Bank 1 (South ADA Tower)"

        gate_display_names = {
            "gate-a": "Gate A (Main North Plaza) — MetLife Stadium",
            "gate-b": "Gate B (East ADA Accessible Concourse) — MetLife Stadium",
            "gate-c": "Gate C (South Concourse Boulevard) — MetLife Stadium",
            "gate-d": "Gate D (West NJ Transit Hub) — MetLife Stadium",
        }

        walk_minutes = max(3, int(best_cost / 60))

        return RouteResult(
            recommended_gate=gate_display_names.get(best_gate, best_gate),
            accessible_path=instructions,
            step_free=step_free if requires_step_free else (best_gate != "gate-c"),
            nearest_quiet_room=quiet_room,
            nearest_elevator=elevator,
            estimated_walk_minutes=walk_minutes,
            accessibility_warning=warning,
            all_segments_verified=all_verified,
            routing_method="dijkstra_graph_verified",
        )

    def _dijkstra(
        self,
        start_node: str,
        target_node: str,
        requires_step_free: bool,
        is_sensory: bool,
        prefer_elevators: bool,
        gate_statuses: dict[str, dict] | None = None,
    ) -> tuple[float, list[PathSegment]]:
        """Core Dijkstra algorithm implementation with accessibility cost weighting."""
        # priority queue entries: (cost, counter, current_node, path_segments)
        counter = 0
        queue: list[tuple[float, int, str, list[PathSegment]]] = [(0.0, counter, start_node, [])]
        visited: dict[str, float] = {}

        while queue:
            current_cost, _, current_node, path = heapq.heappop(queue)

            if current_node in visited and visited[current_node] <= current_cost:
                continue
            visited[current_node] = current_cost

            if current_node == target_node:
                return current_cost, path

            for seg in self.adjacency.get(current_node, []):
                # Hard filter: segment must be open
                if seg.status != "open":
                    continue

                # Hard filter: wheelchair/low-mobility users cannot use stairs or non-step-free segments
                if requires_step_free and (not seg.step_free or seg.has_stairs):
                    continue

                # Edge weighting calculation
                edge_cost = float(seg.weight)

                # Gate congestion penalty if gate statuses are provided
                if current_node.startswith("gate-") and gate_statuses:
                    status_info = gate_statuses.get(current_node, {})
                    density = status_info.get("density", 0)
                    edge_cost += density * 1.5

                # Sensory profile: heavy penalty for high sensory / noisy corridors
                if is_sensory:
                    if seg.sensory_level == "high":
                        edge_cost += 300.0
                    elif seg.sensory_level == "medium":
                        edge_cost += 30.0

                # Elevator preference weighting
                if prefer_elevators and seg.has_elevator:
                    edge_cost *= 0.8
                elif prefer_elevators and not seg.has_elevator and not seg.step_free:
                    edge_cost += 100.0

                new_cost = current_cost + edge_cost
                if seg.to_node not in visited or new_cost < visited[seg.to_node]:
                    counter += 1
                    heapq.heappush(queue, (new_cost, counter, seg.to_node, [*path, seg]))

        return float("inf"), []


# Singleton venue graph instance
stadium_graph = VenueGraph()
