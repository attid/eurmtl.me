// address-generator-worker.js
importScripts('/static/js/stellar-sdk.min.js');

let count = 0;

self.onmessage = function(e) {
    const suffix = e.data.suffix;
    const workerId = e.data.workerId;

    while (true) {
        count++;
        let keypair = StellarSdk.Keypair.random();

        if (keypair.publicKey().endsWith(suffix)) {
            self.postMessage({
                type: 'result',
                publicKey: keypair.publicKey(),
                privateKey: keypair.secret(),
                workerId: workerId
            });
            return;
        }

        if (count % 1000 === 0) {
            self.postMessage({
                type: 'progress',
                count: count,
                workerId: workerId
            });
        }
    }
};
