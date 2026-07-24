/** @odoo-module **/

import { registry } from "@web/core/registry";

function waitForPrint(callback, maxAttempts = 40) {
    let attempts = 0;
    const interval = setInterval(() => {
        attempts++;
        if (document.body.dataset.ridhiraLastPrint || attempts >= maxAttempts) {
            clearInterval(interval);
            delete document.body.dataset.ridhiraLastPrint;
            callback();
        }
    }, 250);
}

registry.category("web_tour.tours").add("pos_kitchen_print_customer_order", {
    test: true,
    steps: () => [
        {
            content: "wait for POS",
            trigger: ".pos",
            run: () => {
                console.log("Tour: POS loaded. Triggering self order simulation...");
                const odooEnv = odoo.__WOWL_DEBUG__.root.env;
                delete document.body.dataset.ridhiraLastPrint;
                fetch('/ridhira_test/simulate_self_order', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        jsonrpc: "2.0",
                        method: "call",
                        params: {
                            config_id: odooEnv.services.pos.config.id,
                            action: 'order'
                        }
                    })
                }).then(r => r.json()).then((res) => {
                    const data = res.result;
                    console.log("Tour: Self order triggered! Order ID:", data.order_id);
                    waitForPrint(() => {
                        console.log("Tour: Order placement print detected! Appending done element...");
                        const div = document.createElement('div');
                        div.id = 'ridhira_tour_done';
                        div.textContent = 'DONE';
                        div.style.display = 'block';
                        div.style.position = 'fixed';
                        div.style.top = '0';
                        div.style.zIndex = '9999';
                        document.body.appendChild(div);
                    });
                });
            }
        },
        {
            content: "finish tour",
            trigger: "#ridhira_tour_done",
            run: () => {
                console.log("Tour finished successfully.");
            }
        }
    ]
});

registry.category("web_tour.tours").add("pos_kitchen_print_customer_cancel", {
    test: true,
    steps: () => [
        {
            content: "wait for POS",
            trigger: ".pos",
            run: () => {
                console.log("Tour: POS loaded. Triggering cancellation simulation...");
                const odooEnv = odoo.__WOWL_DEBUG__.root.env;
                delete document.body.dataset.ridhiraLastPrint;
                
                fetch('/ridhira_test/simulate_self_order', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        jsonrpc: "2.0",
                        method: "call",
                        params: {
                            config_id: odooEnv.services.pos.config.id,
                            action: 'order'
                        }
                    })
                }).then(r => r.json()).then((res) => {
                    const data = res.result;
                    console.log("Tour: Self order triggered for cancel! Order ID:", data.order_id);
                    
                    waitForPrint(() => {
                        console.log("Tour: Order placement print completed! Now cancelling order...");
                        delete document.body.dataset.ridhiraLastPrint;
                        
                        fetch('/ridhira_test/simulate_self_order', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                jsonrpc: "2.0",
                                method: "call",
                                params: {
                                    config_id: odooEnv.services.pos.config.id,
                                    action: 'cancel',
                                    order_id: data.order_id
                                }
                            })
                        }).then(() => {
                            waitForPrint(() => {
                                console.log("Tour: Order cancellation print completed! Appending done element...");
                                const div = document.createElement('div');
                                div.id = 'ridhira_tour_done_cancel';
                                div.textContent = 'DONE2';
                                div.style.display = 'block';
                                div.style.position = 'fixed';
                                div.style.top = '100px';
                                div.style.zIndex = '9999';
                                document.body.appendChild(div);
                            });
                        });
                    });
                });
            }
        },
        {
            content: "finish tour",
            trigger: "#ridhira_tour_done_cancel",
            run: () => {
                console.log("Tour finished successfully.");
            }
        }
    ]
});
