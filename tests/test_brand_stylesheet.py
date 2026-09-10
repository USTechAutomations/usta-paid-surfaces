"""Accept the existing cache-busted shared CSS; reject misleading lookalikes."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from check_brand import c_stylesheet
class SharedStylesheet(unittest.TestCase):
 def test_real_shared_stylesheet_links(self):
  for html in ['<link rel="stylesheet" href="styles.css">','<link href="/feeds/pathlab/styles.css?v=20c6fb0529" rel="stylesheet">',"<link rel='stylesheet' href='../styles.css'>",'<link rel="stylesheet" href="https://ustechautomations.com/feeds/styles.css?v=123">']:
   with self.subTest(html=html):self.assertEqual(c_stylesheet(html),'')
 def test_nonstylesheet_and_unowned_lookalikes(self):
  for html in ['<!-- <link rel="stylesheet" href="styles.css"> -->','<link rel="stylesheet" href="evilstyles.css">','<link rel="stylesheet" href="https://unowned.invalid/styles.css">','<link rel="stylesheet" href="main.css?name=styles.css">','<link rel="stylesheet" href="javascript:styles.css">','<link rel="preload" href="styles.css">']:
   with self.subTest(html=html):self.assertTrue(c_stylesheet(html))
if __name__=='__main__':unittest.main()
