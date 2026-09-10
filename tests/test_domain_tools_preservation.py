import unittest
import test_preserve_independent_overlays as fixture
HEAD, ROW, p = fixture.HEAD, fixture.ROW, fixture.p


class DomainTools(unittest.TestCase):
    setUp = fixture.Preservation.setUp
    def test_domain_tools_retains_all_children_and_excludes_private_recovery(self):
        children = ['/feeds/domain-tools/'+slug+suffix for suffix in ('/', '/offline/')
                    for slug in ('linenbalance','tilemosaic','corecomposite','royaltywaterfall','testlotreplay')]
        row = {'id':'domain-tools-20260909-a','prefixes':['/feeds/domain-tools/'],'sitemap_paths':children}
        p.components({'side_surfaces':[{'prefix':'/feeds','components':[row]}]})
        root = self.source/'site/domain-tools'
        for route in row['prefixes'] + children + ['/feeds/domain-tools/buyer/']:
            folder = self.source/'site'/route.removeprefix('/feeds/')
            folder.mkdir(parents=True,exist_ok=True)
            (folder/'index.html').write_text(route)
        (root/'worker.js').write_bytes(b'owned worker')
        path = self.source/'nginx.conf'
        path.write_text(path.read_text().replace('  location / {',
            '  location = /domain-tools { return 308 /feeds/domain-tools/; }\n'
            '  location ^~ /domain-tools/api/ { return 503; }\n'
            '  location ^~ /domain-tools/ { try_files $uri =404; }\n  location / {'))
        path = self.source/'site/index.html'
        path.write_text(path.read_text().replace('</body>',
            '<section id="domain-tools-independent-20260909-a"><a href="/feeds/domain-tools/">Tools</a></section></body>'))
        path = self.source/'site/sitemap.xml'
        path.write_text(path.read_text().replace('</urlset>', ''.join('<url><loc>https://ustechautomations.com'+url+'</loc></url>'
            for url in row['prefixes']+children)+'</urlset>'))
        receipt = p.overlay(self.source,self.dest,[ROW,row],HEAD)
        p.check_candidate(self.dest,receipt)
        urls = p.sitemap_urls((self.dest/'site/sitemap.xml').read_text())
        for route in children: self.assertIn('https://ustechautomations.com'+route,urls)
        self.assertNotIn('https://ustechautomations.com/feeds/domain-tools/buyer/',urls)
        self.assertEqual(b'owned worker',(self.dest/'site/domain-tools/worker.js').read_bytes())
        self.assertTrue((self.dest/'site/domain-tools/buyer/index.html').is_file())
        with self.assertRaises(ValueError):
            p.components({'side_surfaces':[{'prefix':'/feeds','components':[{**row,'sitemap_paths':children+['/feeds/domain-tools/buyer/']}]}]})
