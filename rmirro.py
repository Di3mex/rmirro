#!/usr/bin/python3

import subprocess
import os
import json
import urllib.request

def pc_run(cmd):
    output = subprocess.getoutput(cmd)
    return output

def rm_run(cmd):
    return pc_run(f"ssh {RM_SSH_NAME} {cmd}")

# TODO: optimize!!! less file access
# TODO: what about using DP in RemarkableFile?
class Remarkable:
    def __init__(self, ssh_name):
        self.ssh_name = ssh_name
        self.ssh_ip = pc_run(f"ssh {self.ssh_name} -v exit 2>&1 | grep 'Connecting to' | cut -d' ' -f4") # e.g. 10.11.99.1
        self.raw_dir_local = os.path.abspath(f"{self.ssh_name}_metadata_rewrite")
        self.raw_dir_remote = "/home/root/.local/share/remarkable/xochitl"
        self.processed_dir_local = f"{self.ssh_name}_rewrite"

    def download_metadata(self):
        pc_run(f"rsync -avzd {self.ssh_name}:{self.raw_dir_remote}/*.metadata {self.raw_dir_local}/")

rm = Remarkable("remarkable")

class AbstractFile:
    def list(self):
        for child in self.children(): # TODO: make use pythonic for ... in self:
            print(child.path())
            child.list()

    def traverse(self, depth_first=False):
        for child in self.children():
            if depth_first:
                yield from child.traverse()
                yield child
            else: # breadth first
                yield child
                yield from child.traverse()

class RemarkableFile(AbstractFile):
    def __init__(self, id=""):
        self.is_root = id == ""
        self.id = id

    # TODO: file size?

    # TODO: make faster
    def metadata(self):
        with open(rm.raw_dir_local + "/" + self.id + ".metadata", "r") as file:
            metadata = json.loads(file.read())
        return metadata

    def children(self):
        children = []
        for filename in os.listdir(rm.raw_dir_local):
            if filename.endswith(".metadata"):
                id = filename.removesuffix(".metadata")
                file = RemarkableFile(id)
                if file.parent().id == self.id:
                    children.append(file)
        return children

    def parent(self):
        if self.is_root:
            return None
        parent_id = self.metadata()["parent"]
        return RemarkableFile(parent_id)

    def name(self):
        if self.is_root:
            return ""
        return self.metadata()["visibleName"]

    def path(self):
        if self.is_root:
            path = ""
        elif self.parent().is_root:
            path = self.name()
        else:
            path = self.parent().path() + "/" + self.name()

        if self.is_file() and not path.endswith(".pdf"):
            path += ".pdf" # add extension (to notes) if TODO: .pdf only?

        return path

    def find(self, path):
        for file in self.traverse():
            if file.path() == path:
                return file
        return None

    def is_directory(self):
        return self.is_root or self.metadata()["type"] == "CollectionType"

    def is_file(self):
        # TODO: verify that it is equivalent to not is_directory()
        return not self.is_root and self.metadata()["type"] == "DocumentType"

    def last_modified(self):
        if self.is_root:
            return 0 # TODO: valid?
        return int(self.metadata()["lastModified"]) // 1000 # s

    def last_accessed(self):
        if self.is_root:
            return 0 # TODO: valid?
        return int(self.metadata()["lastOpened"]) // 1000 # s

    def download(self, recursive=False, verbose=False, update=False):
        # skip this file?
        pc_file = self.on_computer()
        skip = update and pc_file and self.last_modified() <= pc_file.last_modified()

        if skip and verbose:
            print("SKIP", self.path())
        else:
            if verbose:
                print("PULL", self.path())
            path_local = rm.processed_dir_local + "/" + self.path()
            if self.is_directory():
                os.makedirs(path_local, exist_ok=True) # make directories ourselves
            else: # is file
                url = f"http://{rm.ssh_ip}/download/{self.id}/placeholder"
                urllib.request.urlretrieve(url, filename=path_local)
                atime = self.last_accessed() # s
                mtime = self.last_modified() # s
                os.utime(path_local, (atime, mtime)) # sync with access/modification times from RM

        if recursive:
            for child in self.children():
                child.download(recursive=recursive, verbose=verbose, update=update)

    def on_computer(self):
        pc_file = ComputerFile(rm.processed_dir_local).find(self.path())
        return pc_file if pc_file.exists() else None

class ComputerFile(AbstractFile):
    def __init__(self, path):
        self._path = path

    def exists(self):
        return os.path.exists(self.path())

    def path(self):
        return self._path

    def parent(self):
        return ComputerFile(os.path.dirname(self.path()))

    def is_directory(self):
        return os.path.isdir(self.path())

    def is_file(self):
        return os.path.is_file(self.path())

    def children(self):
        if self.is_directory():
            return [ComputerFile(self.path() + "/" + name) for name in os.listdir(self.path())]
        else:
            return []

    def find(self, name):
        return ComputerFile(self.path() + "/" + name)

    def created(self):
        return int(os.path.getctime(self.path())) # s

    def last_accessed(self):
        return int(os.path.getatime(self.path())) # s

    def last_modified(self):
        return int(os.path.getmtime(self.path())) # s

    def on_remarkable(self):
        rm_path = os.path.relpath(self.path(), start=rm.processed_dir_local)
        return RemarkableFile().find(rm_path)

if __name__ == "__main__":
    rm.download_metadata()
    rm_root = RemarkableFile()
    """
    for rm_file in rm_root.traverse():
        pc_file = rm_file.on_computer()
        print("RM:", rm_file.path(), "mod", rm_file.last_modified())
        if pc_file:
            print("PC:", pc_file.path(), "mod", pc_file.last_modified())
        else:
            print("PC:", "DOES NOT EXIST")
        print()
    """

    #print(rm_root.children()[0].on_computer().path())
    #for file in rm_root.traverse(depth_first=False):
        #print(file.path())
    #rm_root.list()
    rm_root.download(recursive=True, verbose=True, update=True)
    #print(rm_root.find("AST4320/Lectures/Week 7.pdf").path())

    #pc_root = ComputerFile(rm.processed_dir_local)
    #print(pc_root.find("AST4320/Lectures/Week 6.pdf").on_remarkable().path())
    #pc_root.list()
    #print(pc_root.find("AST4320/").path())
