// A pseudo-random generator from a seed (mulberry32), for the restarts of the layouts
// (#323): the same seed gives the same draws, so that the same graph, given the same
// time, is laid out the same way. Returns a function giving numbers in [0, 1).
export function seeded(seed) {
    let state = seed >>> 0;
    return () => {
        state = (state + 0x6d2b79f5) >>> 0;
        let t = Math.imul(state ^ (state >>> 15), state | 1);
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}
