from __future__ import annotations
import asyncio
import os
import shutil
from typing import *
from logic.permissions import FilePermissions
from logic.selection import Selection
from logic.workspace import WorkspaceManager

class Transaction:
    def __init__(self) -> None:
        pass
    async def execute(self,progress_callback:None|Callable=None)->None|str:
        raise NotImplementedError()
    def revert(self)->Transaction:
        raise NotImplementedError()
    
    @staticmethod
    def reports_progress()->bool:
        return False
    
    @staticmethod
    def is_atomic()->bool:
        return True

class ChangePermissionTransaction(Transaction):
    def __init__(self,path:str,old_permissions:list,new_permissions:list) -> None:
        self._path=path
        self._old_permissions=old_permissions
        self._new_permissions=new_permissions
    def revert(self) -> Transaction:
        return ChangePermissionTransaction(self._path,self._new_permissions,self._old_permissions)
    async def execute(self,progress_callback:None|Callable=None)->None|str:
        try:
            os.chmod(self._path,FilePermissions.int_from_perms(self._new_permissions))
        except PermissionError:
            return "Operation not permitted"
            


   
def calc_size(path:str)->int:
    if (not os.path.exists(path)):
        return 0
    if (not os.path.isdir(path)):
        return os.path.getsize(path)
    ans=0
    for h in os.walk(path):
        for hh in h[1]+h[2]:
            ans+=os.path.getsize(os.path.join(h[0],hh))
    return ans

def calc_total_size(paths:Iterable[str])->int:
    sum=0
    for h in paths:
        sum+=calc_size(h)
    return sum

class MoveTransaction(Transaction):
    def __init__(self, files:Selection,new_path: str) -> None:
        def prep(val:str)->tuple[str,str]:
            return (val,os.path.join(new_path,os.path.basename(val)))
        
        self._instructions=[prep(h) for h in files.get_list()]

    @staticmethod
    def _from_instructions(instructions:list)->MoveTransaction:
        ans=MoveTransaction.__new__(MoveTransaction)
        ans._instructions=instructions
        return ans

    async def execute(self, progress_callback: None | Callable[..., Any] = None) -> None | str:
        for h in self._instructions:
            if (os.path.exists(h[1])):
                return f"File {h[1]} already exists"
            if (not os.access(os.path.dirname(h[1]),os.W_OK)):
                return f"Cannot create file {h[1]}"
            if (not os.access(h[0],os.R_OK)):
                return f"Cannot read file {h[0]}"
        
        for h in self._instructions:
            shutil.move(h[0],h[1])
        WorkspaceManager.rebuild_all()

    def revert(self)->MoveTransaction:
        return MoveTransaction._from_instructions([(h[1],h[0]) for h in self._instructions])
    
class MoveSingleTransaction(MoveTransaction):
    def __init__(self,path:str,new_path:str) -> None:
        self._instructions=MoveTransaction._from_instructions([(path,new_path)])._instructions



class CopyTransaction(Transaction):
    @staticmethod
    def is_atomic()->bool:
        return False
    
    @staticmethod
    def reports_progress() -> bool:
        return True

    def __init__(self, files:Selection,new_path: str) -> None:
        def prep(val:str)->tuple[str,str]:
            return (val,os.path.join(new_path,os.path.basename(val)))
        self._progress_callback=None
        self._instructions=[prep(h) for h in files.get_list()]

    def set_callback(self,callback:Callable)->None:
        self._progress_callback=callback

    @staticmethod
    def _from_instructions(instructions:list)->CopyTransaction:
        ans=CopyTransaction.__new__(CopyTransaction)
        ans._instructions=instructions
        return ans

    async def execute(self) -> None | str:
        for h in self._instructions:
            if (os.path.exists(h[1])):
                return f"File {h[1]} already exists"
            if (not os.access(os.path.dirname(h[1]),os.W_OK)):
                return f"Cannot create file {h[1]}"
            if (not os.access(h[0],os.R_OK)):
                return f"Cannot read file {h[0]}"

            if (os.path.isdir(h[0])):
                walkres=None
                try:
                    walkres=os.walk(h[0])
                except:
                    return f"Permissoin error while traversing directory {h[0]}"
                for hh in walkres:
                    for hhh in hh[2]+hh[1]:
                        if (not os.access(os.path.join(hh[0],hhh),os.R_OK)):
                            return f"Cannot read file {hhh} from {h[0]}"
                        

        total_size=calc_total_size([h[0] for h in self._instructions])

       


        def real_op():
            i=0
            for h in self._instructions:
                if (os.path.isdir(h[0])):
                    shutil.copytree(h[0],h[1])
                else:
                    shutil.copy(h[0],h[1])

                
        async def reports(cancellation:asyncio.Event)->None:
            while True:
                if (cancellation.is_set()):
                    return
                cur_size=calc_total_size([h[1] for h in self._instructions])
                share=cur_size/total_size
                if (self._progress_callback!=None):
                    self._progress_callback(share)
                await asyncio.sleep(0.2)
                
        cancel_reports=asyncio.Event()
        asyncio.create_task(reports(cancel_reports))
        await asyncio.to_thread(real_op)
        cancel_reports.set()
        WorkspaceManager.rebuild_all()

    def revert(self)->CopyTransaction:
        return RemoveTransaction(Selection([h[1] for h in self._instructions]))

class DoNothingTransaction(Transaction):
    def __init__(self) -> None:
        super().__init__()
    async def execute(self) -> None | str:
        pass
    def revert(self) -> Transaction:
        return DoNothingTransaction()

class RemoveTransaction(Transaction):
    def __init__(self,files:Selection) -> None:
        self._files=files.get_list()
        super().__init__()
    async def execute(self, progress_callback: None | Callable[..., Any] = None) -> None | str:
        if (len(self._files)==0):
            return "No files selected for removal"
        for h in self._files:
            if (not os.path.exists(h)):
                return f"File {h} does not exist"
            if (not os.access(os.path.dirname(h),os.W_OK)):
                return f"Cannot delete file {h}"
        
        for h in self._files:
            if (os.path.isdir(h)):
                shutil.rmtree(h)
            else:
                os.remove(h)
        WorkspaceManager.rebuild_all()

    def revert(self)->DoNothingTransaction:
        return DoNothingTransaction()