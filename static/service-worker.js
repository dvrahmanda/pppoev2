/* Handles Web Push events for the PPPoE monitoring dashboard. */
self.addEventListener('push', (event) => {
    let message = {};
    try {
        message = event.data ? event.data.json() : {};
    } catch (_) {
        message = { body: event.data ? event.data.text() : '' };
    }

    const title = message.title || 'PPPoE Monitoring';
    const options = {
        body: message.body || 'Ada pembaruan status PPPoE.',
        icon: '/static/icons/logo.png',
        badge: '/static/icons/logo.png',
        tag: message.tag || 'pppoe-status',
        renotify: true,
        data: { url: message.url || '/notifications' },
    };

    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const requestedUrl = new URL(event.notification.data?.url || '/notifications', self.location.origin);
    const targetUrl = requestedUrl.origin === self.location.origin
        ? requestedUrl.href
        : new URL('/notifications', self.location.origin).href;

    event.waitUntil((async () => {
        const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
        for (const client of windows) {
            if ('focus' in client) {
                await client.navigate(targetUrl);
                return client.focus();
            }
        }
        return self.clients.openWindow(targetUrl);
    })());
});
