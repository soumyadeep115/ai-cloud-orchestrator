import http from 'k6/http';
import { check, sleep } from 'k6';

const PROFILE = __ENV.PROFILE || 'smoke';
const CLUSTER = __ENV.CLUSTER || 'cluster-a';

const TARGETS = {
    'cluster-a': 'http://localhost:8080',
    'cluster-b': 'http://localhost:8081',
    'cluster-c': 'http://localhost:8082',
};

if (!TARGETS[CLUSTER]) {
    throw new Error(
        `Unknown CLUSTER="${CLUSTER}". Use cluster-a, cluster-b, or cluster-c.`
    );
}

const TARGET_URL = __ENV.TARGET_URL || TARGETS[CLUSTER];

const profiles = {
    smoke: {
        stages: [
            { duration: '15s', target: 2 },
            { duration: '30s', target: 5 },
            { duration: '15s', target: 0 },
        ],
    },

    ramp: {
        stages: [
            { duration: '30s', target: 2 },
            { duration: '60s', target: 5 },
            { duration: '60s', target: 10 },
            { duration: '30s', target: 0 },
        ],
    },

    spike: {
        stages: [
            { duration: '30s', target: 2 },
            { duration: '30s', target: 5 },
            { duration: '10s', target: 20 },
            { duration: '30s', target: 20 },
            { duration: '30s', target: 2 },
            { duration: '30s', target: 0 },
        ],
    },

    surge: {
        // for live static-vs-ML comparison: quiet lull, sharp surge,
        // long plateau, drop. ~7m20s total.
        stages: [
            { duration: '90s', target: 2 },
            { duration: '10s', target: 20 },
            { duration: '4m',  target: 20 },
            { duration: '10s', target: 2 },
            { duration: '90s', target: 2 },
        ],
    },

    // Longer profiles for ML dataset generation — run these unattended
    // for hours, not seconds, so the poller captures real variation.

    idle: {
        // near-zero load baseline: what "normal, nothing happening" looks like
        stages: [
            { duration: '20m', target: 1 },
        ],
    },

    sustained: {
        // flat, sustained moderate load for a long stretch
        stages: [
            { duration: '2m', target: 8 },
            { duration: '20m', target: 8 },
            { duration: '2m', target: 0 },
        ],
    },

    periodic: {
        // compressed "daily cycle": repeats low->high->low several times
        // so the model can learn a recurring pattern, not just one event
        stages: [
            { duration: '3m', target: 2 },
            { duration: '3m', target: 12 },
            { duration: '3m', target: 2 },
            { duration: '3m', target: 12 },
            { duration: '3m', target: 2 },
            { duration: '3m', target: 12 },
            { duration: '3m', target: 2 },
        ],
    },

    long_ramp: {
        // slow, steady climb and decline — good for "increasing traffic" /
        // "traffic decrease" patterns distinct from a sudden spike
        stages: [
            { duration: '5m', target: 3 },
            { duration: '10m', target: 15 },
            { duration: '5m', target: 15 },
            { duration: '10m', target: 3 },
        ],
    },
};

if (!profiles[PROFILE]) {
    throw new Error(
        `Unknown PROFILE="${PROFILE}". Use one of: ${Object.keys(profiles).join(', ')}.`
    );
}

export const options = {
    stages: profiles[PROFILE].stages,

    // New connection per request so kube-proxy balances every request across
    // pods instead of each VU staying pinned to one pod via keep-alive.
    noConnectionReuse: (__ENV.NO_CONN_REUSE || 'true') === 'true',

    thresholds: {
        http_req_failed: ['rate<0.05'],
        http_req_duration: ['p(95)<1000'],
    },

    tags: {
        cluster: CLUSTER,
    },
};

export default function () {
    const response = http.get(`${TARGET_URL}/`);

    check(response, {
        'HTTP status is 200': (r) => r.status === 200,
    });

    sleep(1);
}