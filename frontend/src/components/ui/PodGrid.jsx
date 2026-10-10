import { LIVE_MAX_REPLICAS, MAX_REPLICAS, MIN_REPLICAS } from "../../config";
import { isNum } from "../../lib/format";

/** One square per possible replica slot: filled = running, hatched = above the live cap. */
export default function PodGrid({ pods, desired }) {
  const count = isNum(pods) ? pods : 0;
  const slots = Math.max(MAX_REPLICAS, count);
  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {Array.from({ length: slots }, (_, i) => {
          const active = i < count;
          const locked = !active && i >= LIVE_MAX_REPLICAS;
          return (
            <div
              key={i}
              title={active ? `pod ${i + 1}` : locked ? "above the live scaling cap" : "free slot"}
              className={`w-9 h-9 rounded-md border flex items-center justify-center text-[10px] font-mono transition-colors ${
                active
                  ? "border-violet/60 bg-violet/20 text-violet pod-pop"
                  : locked
                    ? "border-hairline border-dashed text-text-muted/25 bg-hairline/30"
                    : "border-hairline border-dashed text-text-muted/40"
              }`}
            >
              {i + 1}
            </div>
          );
        })}
      </div>
      <div className="mt-3 text-[11px] font-mono text-text-muted flex flex-wrap gap-x-4">
        <span>
          <span className="text-text-primary">{isNum(pods) ? pods : "—"}</span> running
        </span>
        <span>min {MIN_REPLICAS}</span>
        <span>live cap {LIVE_MAX_REPLICAS}</span>
        <span>limit {MAX_REPLICAS}</span>
        {isNum(desired) && isNum(pods) && desired !== pods && <span className="text-warn">orchestrator wants {desired}</span>}
      </div>
    </div>
  );
}
