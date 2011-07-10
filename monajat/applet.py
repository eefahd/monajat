# -*- coding: utf-8 -*-
import os, os.path
import itl
from monajat import Monajat
from utils import init_dbus
import gettext

import glib
import gtk
import pynotify
import cgi
import math
import json

class ConfigDlg(gtk.Dialog):
  def __init__(self, applet):
    gtk.Dialog.__init__(self)
    self.applet=applet
    self.m=applet.m
    self.connect('delete-event', lambda w,*a: w.hide() or True)
    self.connect('response', lambda w,*a: w.hide() or True)
    self.set_title(_('Monajat Configuration'))
    self.add_button(_('Cancel'), gtk.RESPONSE_CANCEL)
    self.add_button(_('Save'), gtk.RESPONSE_OK)
    tabs=gtk.Notebook()
    self.get_content_area().add(tabs)
    vb=gtk.VBox()
    tabs.append_page(vb, gtk.Label(_('Generic')))
    self.auto_start = b = gtk.CheckButton(_("Auto start"))
    self.auto_start.set_active(not os.path.exists(self.applet.skip_auto_fn))
    vb.pack_start(b, False, False, 2)
    self.show_merits = b = gtk.CheckButton(_("Show merits"))
    self.show_merits.set_active(self.applet.conf['show_merits'])
    vb.pack_start(b, False, False, 2)
    hb = gtk.HBox()
    vb.pack_start(hb, True, True, 2)
    hb.pack_start(gtk.Label(_('Language:')), False, False, 2)
    self.lang = b = gtk.combo_box_new_text()
    hb.pack_start(b, False, False, 2)
    selected = 0
    for i,j in enumerate(self.applet.m.langs):
      b.append_text(j)
      if self.m.lang==j: selected=i
    b.set_active(selected)
    
    hb = gtk.HBox()
    vb.pack_start(hb, True, True, 2)
    hb.pack_start(gtk.Label(_('Time:')), False, False, 2)
    self.timeout = b = gtk.SpinButton(gtk.Adjustment(5, 0, 90, 5, 5))
    b.set_value(self.applet.conf['minutes'])
    hb.pack_start(b, False, False, 2)
    hb.pack_start(gtk.Label(_('minutes')), False, False, 2)

    vb=gtk.VBox()
    tabs.append_page(vb, gtk.Label(_('Location')))
    
    s = gtk.TreeStore(str, bool, int) # label, is_city, id
    self.cities_tree=tree=gtk.TreeView(s)
    col=gtk.TreeViewColumn('Location', gtk.CellRendererText(), text=0)
    col.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
    tree.insert_column(col, -1)
    tree.set_enable_search(True)
    tree.set_search_column(0)
    tree.set_headers_visible(False)
    tree.set_tooltip_column(0)
    
    scroll=gtk.ScrolledWindow()
    scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_ALWAYS)
    scroll.add(tree)
    vb.pack_start(scroll, True, True, 2)
    self._fill_cities()

  def _fill_cities(self):
    tree=self.cities_tree
    s=tree.get_model()
    rows=self.m.cities_c.execute('SELECT * FROM cities')
    country, country_i = None, None
    state, state_i=None, None
    for R in rows:
      r=dict(R)
      if country!=r['country']:
        country_i=s.append(None,(r['country'], False, 0))
      if state!=r['state']:
        state_i=s.append(country_i,(r['state'], False, 0))
      country=r['country']
      state=r['state']
      #city=u'%s - %s' % (r['name'], r['local_name']) # FIXME: should be locale with e
      city=r['name']
      s.append(state_i,(city, True, 0))

  def run(self, *a, **kw):
    self.auto_start.set_active(not os.path.exists(self.applet.skip_auto_fn))
    return gtk.Dialog.run(self, *a, **kw)

class applet(object):
  skip_auto_fn=os.path.expanduser('~/.monajat-applet-skip-auto')
  def __init__(self):
    self.conf_dlg=None
    self.minutes_counter=0
    self.m=Monajat() # you may pass width like 20 chars
    self.load_conf()
    self.prayer_items=[]
    kw=self.conf_to_prayer_args()
    self.prayer=itl.PrayerTimes(**kw)
    ld=os.path.join(self.m.get_prefix(),'..','locale')
    gettext.install('monajat', ld, unicode=0)
    self.clip1=gtk.Clipboard(selection="CLIPBOARD")
    self.clip2=gtk.Clipboard(selection="PRIMARY")
    self.init_about_dialog()
    self.init_menu()
    #self.s=gtk.status_icon_new_from_file(os.path.join(self.m.get_prefix(),'monajat.svg'))
    #self.s.connect('popup-menu',self.popup_cb)
    #self.s.connect('activate',self.next_cb)
    pynotify.init('MonajatApplet')
    self.notifycaps = pynotify.get_server_caps ()
    print self.notifycaps
    self.notify=pynotify.Notification("MonajatApplet")
    ##self.notify.attach_to_status_icon(self.s)
    self.notify.set_property('icon-name','monajat')
    self.notify.set_property('summary', _("Monajat") )
    if 'actions' in self.notifycaps:
      self.notify.add_action("previous", _("previous"), self.notify_cb)
      self.notify.add_action("next", _("next"), self.notify_cb)
      self.notify.add_action("copy", _("copy"), self.notify_cb)
    #self.notify.set_timeout(60)
    self.statusicon = gtk.StatusIcon ()
    self.statusicon.connect('popup-menu',self.popup_cb)
    self.statusicon.connect('activate',self.next_cb)
    self.statusicon.set_title(_("Monajat"))
    self.statusicon.set_from_file(os.path.join(self.m.get_prefix(),'monajat.svg'))

    glib.timeout_add_seconds(10, self.start_timer)

  def config_cb(self, *a):
    if self.conf_dlg==None:
      self.conf_dlg=ConfigDlg(self)
      self.conf_dlg.show_all()
    r=self.conf_dlg.run()
    if r==gtk.RESPONSE_OK:
      self.save_auto_start()
      self.save_conf()

  def default_conf(self):
    self.conf={}
    self.conf['show_merits']='1'
    self.conf['lang']=self.m.lang
    self.conf['minutes']='10'

  def conf_to_prayer_args(self):
    kw={}
    if not self.conf.has_key('city_id'): return kw
    c=self.m.cities_c
    try: c_id=int(self.conf['city_id'])
    except ValueError: return kw
    except TypeError: return kw
    r=c.execute('SELECT * FROM cities AS c LEFT JOIN dst as d ON d.id=dst WHERE c.id=?', (c_id,)).fetchone()
    kw=dict(r)
    kw["tz"]=kw["utc"]
    dst=kw["dst"]
    if not dst: kw["dst"]=0
    else:
      # FIXME: allow DST to be fetched from machine local setting
      # FIXME: add DST logic here
      kw["dst"]=1
    print kw
    #lat=21.43, lon=39.77, tz=3.0, dst=0, alt=0, pressure=1010, temp=10
    return kw


  def parse_conf(self, s):
    self.default_conf()
    l1=map(lambda k: k.split('=',1), filter(lambda j: j,map(lambda i: i.strip(),s.splitlines())) )
    l2=map(lambda a: (a[0].strip(),a[1].strip()),filter(lambda j: len(j)==2,l1))
    r=dict(l2)
    self.conf.update(dict(l2))
    return len(l1)==len(l2)

  def load_conf(self):
    s=''
    fn=os.path.expanduser('~/.monajat-applet.rc')
    if os.path.exists(fn):
      try: s=open(fn,'rt').read()
      except OSError: pass
    self.parse_conf(s)
    # fix types
    try: self.conf['minutes']=math.ceil(float(self.conf['minutes'])/5.0)*5
    except ValueError: self.conf['minutes']=0
    try: self.conf['show_merits']=int(self.conf['show_merits']) 
    except ValueError: self.conf['show_merits']=1
    self.m.set_lang(self.conf['lang'])
    self.m.clear()

  def save_conf(self):
    self.conf['show_merits']=int(self.conf_dlg.show_merits.get_active())
    self.conf['lang']=self.conf_dlg.lang.get_active_text()
    self.conf['minutes']=int(self.conf_dlg.timeout.get_value())
    print "** saving conf", self.conf
    fn=os.path.expanduser('~/.monajat-applet.rc')
    s='\n'.join(map(lambda k: "%s=%s" % (k,str(self.conf[k])), self.conf.keys()))
    try: open(fn,'wt').write(s)
    except OSError: pass

  def start_timer(self, *args):
    glib.timeout_add_seconds(60, self.timed_cb)
    self.next_cb()
    return False

  def timed_cb(self, *args):
    if self.prayer.update():
      self.update_prayer()
    if not self.conf['minutes']: return True
    if self.minutes_counter % self.conf['minutes'] == 0:
      self.minutes_counter=1
      self.next_cb()
    else:
      self.minutes_counter+=1
    return True

  def hide_cb(self, w, *args): w.hide(); return True

  def render_body(self, m):
    merits=m['merits']
    if not self.conf['show_merits']: merits=None
    if "body-markup" in self.notifycaps:
      body=cgi.escape(m['text'])
      if merits: body+="""\n\n<b>%s</b>: %s""" % (_("Its Merits"),cgi.escape(merits))
    else:
      body=m['text']
      if merits: body+="""\n\n** %s **: %s""" % (_("Its Merits"),merits)
    
    if "body-hyperlinks" in self.notifycaps:
      L=[]
      links=m.get('links',u'').split(u'\n')
      for l in links:
        ll=l.split(u'\t',1)
        url=cgi.escape(ll[0])
        if len(ll)>1: t=cgi.escape(ll[1])
        else: t=url
        L.append(u"""<a href='%s'>%s</a>""" % (url,t))
      l=u"\n\n".join(L)
      body+=u"\n\n"+l
    self.notify.set_property('body', body)

  def dbus_cb(self, *args):
    self.minutes_counter=1
    self.next_cb()
    return 0

  def next_cb(self,*args):
    try: self.notify.close()
    except glib.GError: pass
    self.render_body(self.m.go_forward())
    self.notify.show()
    return True

  def prev_cb(self, *args):
    try: self.notify.close()
    except glib.GError: pass
    self.render_body(self.m.go_back())
    self.notify.show()

  def copy_cb(self,*args):
    r=self.m.get_current()
    self.clip1.set_text(r['text'])
    self.clip2.set_text(r['text'])

  def init_about_dialog(self):
    # FIXME: please add more the authors
    self.about_dlg=gtk.AboutDialog()
    self.about_dlg.set_default_response(gtk.RESPONSE_CLOSE)
    self.about_dlg.connect('delete-event', self.hide_cb)
    self.about_dlg.connect('response', self.hide_cb)
    try: self.about_dlg.set_program_name("Monajat")
    except: pass
    self.about_dlg.set_name(_("Monajat"))
    #self.about_dlg.set_version(version)
    self.about_dlg.set_copyright("Copyright © 2009 sabily.org")
    self.about_dlg.set_comments(_("Monajat supplications"))
    self.about_dlg.set_license("""\
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
""")
    self.about_dlg.set_website("https://launchpad.net/monajat")
    self.about_dlg.set_website_label("Monajat web site")
    self.about_dlg.set_authors(["Fadi al-katout <cutout33@gmail.com>",
                                "Muayyad Saleh Alsadi <alsadi@ojuba.org>",
                                "Mahyuddin Susanto <udienz@ubuntu.com>",
                                "عبدالرحيم دوبيلار <abdulrahiem@sabi.li>",
                                "أحمد المحمودي (Ahmed El-Mahmoudy) <aelmahmoudy@sabily.org>"])
  def save_auto_start(self):
    b=self.conf_dlg.auto_start.get_active()
    if b and os.path.exists(self.skip_auto_fn):
      try: os.unlink(self.skip_auto_fn)
      except OSError: pass
    elif not b:
      open(self.skip_auto_fn,'wt').close()
  
  def update_prayer(self):
    if not self.prayer_items: return
    pt=self.prayer.get_prayers()
    j=0
    for p,t in zip(["", "Fajr", "Dhuhr", "Asr", "Maghrib", "Isha'a"], pt):
      if not p: continue
      i = gtk.MenuItem
      self.prayer_items[j].set_label(u"%s %s" % (p, t.format(),))
      j+=1
  
  def init_menu(self):
    self.menu = gtk.Menu()
    i = gtk.ImageMenuItem(gtk.STOCK_COPY)
    i.connect('activate', self.copy_cb)
    self.menu.add(i)

    i = gtk.ImageMenuItem(gtk.STOCK_GO_FORWARD)
    i.connect('activate', self.next_cb)
    self.menu.add(i)

    i = gtk.ImageMenuItem(gtk.STOCK_GO_BACK)
    i.connect('activate', self.prev_cb)
    self.menu.add(i)

    self.menu.add(gtk.SeparatorMenuItem())

    self.prayer_items=[]
    for j in range(5):
      i = gtk.MenuItem("-")
      self.prayer_items.append(i)
      self.menu.add(i)
    self.update_prayer()

    self.menu.add(gtk.SeparatorMenuItem())
    
    i = gtk.MenuItem(_("Configure"))
    i.connect('activate', self.config_cb)
    self.menu.add(i)
    
    self.menu.add(gtk.SeparatorMenuItem())

    i = gtk.ImageMenuItem(gtk.STOCK_ABOUT)
    i.connect('activate', lambda *args: self.about_dlg.run())
    self.menu.add(i)
    
    i = gtk.ImageMenuItem(gtk.STOCK_QUIT)
    i.connect('activate', gtk.main_quit)
    self.menu.add(i)

    self.menu.show_all()

  def popup_cb(self, s, button, time):
    self.menu.popup(None, None, gtk.status_icon_position_menu, button, time, s)

  def time_set_cb(self, m, t):
    self.conf['minutes']=t
    self.minutes_counter=1
    self.save_conf()

  def lang_cb(self, m, l):
    if not m.get_active(): return
    self.m.set_lang(l)
    self.save_conf()

  def notify_cb(self,notify,action):
    try: self.notify.close()
    except glib.GError: pass
    if action=="exit": gtk.main_quit()
    elif action=="copy": self.copy_cb()
    elif action=="next": self.next_cb()
    elif action=="previous": self.prev_cb()

def applet_main():
  a=applet()
  init_dbus(a.dbus_cb)
  gtk.main()

if __name__ == "__main__":
  applet_main()

