#   Copyright (c) 2009-2011, Konstantin Yegupov
#   All rights reserved.
#
#   Redistribution and use in source and binary forms, with or without modification,
#   are permitted provided that the following conditions are met:
#
#       * Redistributions of source code must retain the above copyright notice,
#         this list of conditions and the following disclaimer.
#
#       * Redistributions in binary form must reproduce the above copyright notice,
#         this list of conditions and the following disclaimer in the documentation
#         and/or other materials provided with the distribution.
#
#       * The name of the author may not be used to endorse or promote products
#         derived from this software without specific prior written permission. 
#
#   THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
#   ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
#   WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#   DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
#   ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
#   (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
#   LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
#   ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#   (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
#   SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os, os.path
import zipfile
import glob

import UnRAR2

import StringIO

from ConfigParser import RawConfigParser

import Image

img_extensions = ['jpg', 'gif', 'png']

class UnsupportedFileTypeError:
    pass
    
class FilenameNotFoundError:
    pass

class AZNamer:
    def __init__(self, caps=True):
        self.caps = caps
        self.x = [self.a()]
        
    def a(self):
        if self.caps: return "A"
        return "a"
    
    def next(self):
        res = ''.join(self.x)
        i= len(self.x)-1
        while i>0 and self.x[i].lower()=='z':
            i-=1
        if i==-1:
            self.x = [self.a()] * (len(self.x)+1)
        else:
            self.x[i] = chr(ord(self.x[i])+1)
            for j in range(i+1, len(self.x)):
                self.x[i] = self.a()
        return res

def ComicBook(path):
    if not os.path.isfile(path):
        if os.path.isdir(path):
            return DirComicBook(path)
    else:
        ext = os.path.splitext(path)[1].lower()[1:]
        if ext in ['zip','cbz']:
            return ZipComicBook(path)
        elif ext in ['rar','cbr']:
            return RarComicBook(path)
        elif ext in img_extensions:
            return SingleFileComicBook(path)
        else:
            raise UnsupportedFileTypeError
            

class BaseComicBook:
    def __init__(self, path):
        self.path = path
        
    @property
    def pretty_name(self):
        return self.path.split(os.sep)[-1]

    def __len__(self):
        return len(self.filenames)
        
    def get_filename(self, page):
        return os.path.split(self.filenames[page])[1]

    def get_file(self, page):
        return self.get_file_by_name(self.filenames[page])
        
    def get_panel_file(self):
        return self.get_file_by_name('panels.ini')

    def load_panels(self, page_id):
        name = self.get_filename(page_id)
        config = RawConfigParser()
        try:
            config.readfp(self.get_panel_file())
        except:
            pass
        opts = config.options(name)
        opts.sort()
        panels = []
        if config.get(name, "format")=="rect":
            for pn in opts:
                if pn.startswith('panel'):
                    line = config.get(name, pn)
                    panels.append([int(x) for x in line.strip().split(',')])
        elif config.get(name, "format")=="grid":
            rows = {}
            cols = {}
            for n in opts:
                if n.startswith('grid_h_'):
                    rows[n[7:]] = int(config.get(name, n))
                if n.startswith('grid_v_'):
                    cols[n[7:]] = int(config.get(name, n))
            for pn in opts:
                if pn.startswith('panel'):
                    line = config.get(name, pn)
                    h,v = line.split(',')
                    r0,r1 = h.split('-')
                    y0,y1 = rows[r0.lower()],rows[r1.lower()]
                    c0,c1 = v.split('-')
                    x0,x1 = cols[c0],cols[c1]
                    panels.append([x0,y0,x1,y1])
        else:
            raise NotImplementedError
        if len(panels)==0:
            fil = self.get_file(page_id)
            image = Image.open(fil)
            panels.append([0,0,image.size[0], image.size[1]])
        return panels
        
    def save_panels(self, page_id, panels, mode = "rect"):
        if not self.writable:
            raise TypeError, 'not a writable comic archive'
        fn = self.get_filename(page_id)
        res = ""
        config = RawConfigParser()
        try:
            config.readfp(self.get_panel_file())
        except:
            pass
        config.remove_section(fn)
        config.add_section(fn)
        if mode=="rect":
            config.set(fn, "format", "rect")
            for i,p in enumerate(panels):
                config.set(fn, "panel%02d" % i, "%s,%s,%s,%s" % tuple(p))
        elif mode=="grid":
            config.set(fn, "format", "grid")
            rows = {}
            cols = {}
            for p in panels:
                x0,y0,x1,y1 = p
                cols[x0] = ''
                cols[x1] = ''
                rows[y0] = ''
                rows[y1] = ''
            az = AZNamer(True)
            for r in sorted(rows.keys()):
                rows[r] = az.next()
                config.set(fn, "grid_h_"+rows[r], r)
            az = AZNamer(False)
            for c in sorted(cols.keys()):
                cols[c] = az.next()
                config.set(fn, "grid_v_"+cols[c], c)
            for i,p in enumerate(panels):
                x0,y0,x1,y1 = p
                c0 = cols[x0]
                c1 = cols[x1]
                r0 = rows[y0]
                r1 = rows[y1]
                config.set(fn, "panel%02d" % i, "%s-%s,%s-%s" % (r0,r1,c0,c1))
        else:
            raise NotImplementedError
        out = StringIO.StringIO()
        config.write(out)
        self.add_file('panels.ini', out.getvalue())
        self.has_segmentation = True
        return res

class ZipComicBook(BaseComicBook):
    def __init__(self, path):
        BaseComicBook.__init__(self, path)
        self.zf = zipfile.ZipFile(path, 'r', zipfile.ZIP_DEFLATED)
        self.writable = False
        namelist = self.zf.namelist()
        self.has_segmentation = "panels.ini" in namelist
        self.filenames = [fn for fn in namelist if os.path.splitext(fn)[1][1:] in img_extensions]
        self.filenames.sort()

    def get_file_by_name(self, name):
        return StringIO.StringIO(self.zf.read(name))
        
    @staticmethod
    def create_copy(path, comix2):
        zf = zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED)
        for i in range(len(comix2)):
            zf.writestr(comix2.get_filename(i), comix2.get_file(i).read())
        zf.close()
        return ZipComicBook(path)
        
    def add_file(self, name, bytez):
        self.zf.writestr(name, bytez)
        self.zf.close()
        self.zf = zipfile.ZipFile(self.path, 'a', zipfile.ZIP_DEFLATED)

class RarComicBook(BaseComicBook):
    def __init__(self, path):
        BaseComicBook.__init__(self, path)
        rf = UnRAR2.RarFile(path)
        namelist = [f.filename for f in rf.infoiter()]
        self.has_segmentation = "panels.ini" in namelist
        self.filenames = [fn for fn in namelist if os.path.splitext(fn)[1][1:] in img_extensions]
        self.filenames.sort()
        del rf
        self.writable = False

    def get_file_by_name(self, name):
        rf = UnRAR2.RarFile(self.path)
        res = None
        loaded = rf.read_files(name)
        res = StringIO.StringIO(loaded[0][1])
        del rf
        return res
        
class DirComicBook(BaseComicBook):
    def __init__(self, path):
        BaseComicBook.__init__(self, path)
        try:
            tmp = open(os.path.join(path, 'test__.tmp'), 'w')
            tmp.close()
            os.unlink(os.path.join(path, 'test__.tmp'))
            self.writable = True
        except IOError:
            self.writable = False
        mask = os.path.join(os.path.normpath(path), '*')
        namelist = [fn[len(mask)-1:] for fn in glob.glob(mask)]
        self.has_segmentation = "panels.ini" in namelist
        self.filenames = [fn for fn in namelist if os.path.splitext(fn)[1][1:] in img_extensions]
        self.filenames.sort()

    def get_file_by_name(self, name):
        return open(os.path.join(self.path, name), 'rb')
        
    def add_file(self, name, bytez):
        open(os.path.join(self.path, name), 'wb').write(bytez)

    @staticmethod
    def create_copy(path, comix2):
        path = os.path.normpath(path)
        try:
            os.makedirs(path)
        except Exception:
            pass
        for i in range(len(comix2)):
            open(os.path.join(path, comix2.get_filename(i)), 'wb').write(comix2.get_file(i).read())
        return DirComicBook(path)

class SingleFileComicBook(BaseComicBook):
    def __init__(self, path):
        BaseComicBook.__init__(self, path)
        try:
            tmp = open(path+"_test__.tmp", "wb")
            tmp.close()
            os.unlink(path+"_test__.tmp")
            self.writable = True
        except IOError:
            self.writable = False
        try:
            self.get_file_by_name("panels.ini")
            self.has_segmentation = True
        except:
            self.has_segmentation = False
        self.filenames = [path]

    def get_file_by_name(self, name):
        basepath, simple_name = os.path.split(self.filenames[0])
        if name==self.filenames[0] or name==simple_name:
            return open(self.filenames[0], 'rb')
        else:
            return open(self.filenames[0]+"_"+name, 'rb')
        
    def add_file(self, name, bytez):
        open(self.filenames[0]+"_"+name, 'wb').write(bytez)

if __name__=="__main__":
    try:
        import debug_scripts
    except ImportError:
        debug_scripts = False
    if debug_scripts:
        debug_scripts.go()
