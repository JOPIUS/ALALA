from proxies import ProxyManager
pm = ProxyManager()
print('Loaded proxies:', len(pm.proxies))
for i in range(5):
    p = pm.next_proxy()
    print(i+1, p)
