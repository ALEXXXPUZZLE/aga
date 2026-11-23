from fastapi import FastAPI, APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field, field_validator
from typing import Optional


# =========================
# MODELS
# =========================

class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def validate(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Название не может состоять из пробелов")
        return value.strip()


class Task(BaseModel):
    task_id: int
    name: str = Field(min_length=1, max_length=100)
    completed: bool


class TaskUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    completed: bool

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Название не может состоять из пробелов")
        return value.strip()


class TaskPatch(BaseModel):
    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100
    )
    completed: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        if not value.strip():
            raise ValueError("Название не может состоять из пробелов")

        return value.strip()


# =========================
# TASK MANAGER
# =========================

class TaskManager:

    def __init__(self) -> None:
        self.tasks: list[Task] = []
        self.next_id: int = 1

    def get_tasks(self) -> list[Task]:
        return self.tasks

    def add_task(self, task_data: TaskCreate) -> Task:
        task = Task(
            task_id=self.next_id,
            name=task_data.name,
            completed=False
        )

        self.next_id += 1
        self.tasks.append(task)

        return task

    def find_task(self, task_id: int) -> Optional[Task]:
        for task in self.tasks:
            if task.task_id == task_id:
                return task

        return None

    def remove_task(self, task_id: int) -> Optional[Task]:
        for task in self.tasks:
            if task.task_id == task_id:
                self.tasks.remove(task)
                return task

        return None

    def update_task(
        self,
        task_id: int,
        updated_task: TaskUpdate
    ) -> Optional[Task]:

        task = self.find_task(task_id)

        if task is None:
            return None

        task.name = updated_task.name
        task.completed = updated_task.completed

        return task

    def patch_task(
        self,
        task_id: int,
        patched_task: TaskPatch
    ) -> Optional[Task]:

        task = self.find_task(task_id)

        if task is None:
            return None

        changes = patched_task.model_dump(exclude_unset=True)

        for field, value in changes.items():
            setattr(task, field, value)

        return task

    def get_completed_task(self, completed: bool) -> list[Task]:
        result: list[Task] = []

        for task in self.tasks:
            if task.completed == completed:
                result.append(task)

        return result

    def get_name(self, name: str) -> list[Task]:
        result: list[Task] = []

        for task in self.tasks:
            if name.lower() in task.name.lower():
                result.append(task)

        return result

    def get_filtered_tasks(
        self,
        name: str,
        completed: bool
    ) -> list[Task]:

        result: list[Task] = []

        for task in self.tasks:
            if (
                name.lower() in task.name.lower()
                and task.completed == completed
            ):
                result.append(task)

        return result

    def get_sorted_tasks(self) -> list[Task]:
        non_completed: list[Task] = []
        completed: list[Task] = []

        for task in self.tasks:
            if task.completed:
                completed.append(task)
            else:
                non_completed.append(task)

        return non_completed + completed

    def get_sorted_by_id(self) -> list[Task]:
        return sorted(
            self.tasks,
            key=lambda task: task.task_id
        )

    def get_sorted_by_name(self) -> list[Task]:
        return sorted(
            self.tasks,
            key=lambda task: task.name.lower()
        )

    def get_tasks_page(self, skip: int, limit: int) -> list[Task]:
        return self.tasks[skip:skip + limit]

    def get_tasks_sort(self, sort_by: str) -> Optional[list[Task]]:
        if sort_by.lower() == "id":
            return self.get_sorted_by_id()

        elif sort_by.lower() == "name":
            return self.get_sorted_by_name()

        elif sort_by.lower() == "completed":
            return self.get_sorted_tasks()

        return None


# =========================
# DEPENDENCIES
# =========================

manager = TaskManager()
allowed = False


def get_manager() -> TaskManager:
    return manager


def check_access() -> bool:
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail="Доступ запрещён"
        )

    return True


def get_completed(completed: Optional[bool] = None) -> Optional[bool]:
    return completed


def get_name(name: Optional[str] = None) -> Optional[str]:
    return name


# =========================
# FASTAPI
# =========================

app = FastAPI()
router = APIRouter(prefix="/tasks")


# =========================
# GET ROUTES
# =========================

@router.get("/", response_model=list[Task])
def get_task(
    manager: TaskManager = Depends(get_manager),
    access: bool = Depends(check_access),
    completed: Optional[bool] = Depends(get_completed),
    name: Optional[str] = Depends(get_name)
) -> list[Task]:

    if name is not None and completed is not None:
        return manager.get_filtered_tasks(name, completed)

    if name is not None:
        return manager.get_name(name)

    if completed is not None:
        return manager.get_completed_task(completed)

    return manager.get_tasks()


@router.get("/sorted", response_model=list[Task])
def get_sorted_tasks(
    manager: TaskManager = Depends(get_manager)
) -> list[Task]:
    return manager.get_sorted_tasks()


@router.get("/sorted-by-id", response_model=list[Task])
def get_sorted_by_id(
    manager: TaskManager = Depends(get_manager)
) -> list[Task]:
    return manager.get_sorted_by_id()


@router.get("/sorted-by-name", response_model=list[Task])
def get_sorted_by_name(
    manager: TaskManager = Depends(get_manager)
) -> list[Task]:
    return manager.get_sorted_by_name()


@router.get("/page", response_model=list[Task])
def get_tasks_page(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    manager: TaskManager = Depends(get_manager)
) -> list[Task]:
    return manager.get_tasks_page(skip, limit)


@router.get("/sort", response_model=list[Task])
def get_tasks_sort(
    sort_by: str = Query(default="id"),
    manager: TaskManager = Depends(get_manager)
) -> list[Task]:

    result = manager.get_tasks_sort(sort_by)

    if result is None:
        raise HTTPException(
            status_code=400,
            detail="Неизвестный тип сортировки"
        )

    return result


# Динамический маршрут размещаем после статических

@router.get("/{task_id}", response_model=Task)
def find_tasks(
    task_id: int,
    manager: TaskManager = Depends(get_manager)
) -> Task:

    result = manager.find_task(task_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Такая задача не найдена"
        )

    return result


# =========================
# POST
# =========================

@router.post("/", response_model=Task, status_code=201)
def add_task(
    task: TaskCreate,
    manager: TaskManager = Depends(get_manager)
) -> Task:
    return manager.add_task(task)


# =========================
# DELETE
# =========================

@router.delete("/{task_id}", status_code=204)
def remove_task(
    task_id: int,
    manager: TaskManager = Depends(get_manager)
) -> None:

    result = manager.remove_task(task_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Задача не найдена"
        )

    return None


# =========================
# PUT
# =========================

@router.put("/{task_id}", response_model=Task)
def update_task(
    task_id: int,
    updated_task: TaskUpdate,
    manager: TaskManager = Depends(get_manager)
) -> Task:

    result = manager.update_task(task_id, updated_task)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Задача не найдена"
        )

    return result


# =========================
# PATCH
# =========================

@router.patch("/{task_id}", response_model=Task)
def patch_task(
    task_id: int,
    patched_task: TaskPatch,
    manager: TaskManager = Depends(get_manager)
) -> Task:

    if not patched_task.model_fields_set:
        raise HTTPException(
            status_code=400,
            detail="Надо передать хотя бы одно значение"
        )

    result = manager.patch_task(task_id, patched_task)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Задача не найдена"
        )

    return result


# =========================
# REGISTER ROUTER
# =========================

app.include_router(router)
