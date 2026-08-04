from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.core.push import send_push_to_user

from .forms import ThreadCommentForm, ThreadForm
from .models import Thread, ThreadComment, ThreadRead
from .permissions import can_delete_comment, can_hard_delete_comment, can_moderate_thread, can_post, is_moderator


def _build_comment_tree(thread, user):
    """Convierte la lista plana de comentarios en un árbol anidado sin N+1
    queries: se trae todo de una vez y se enlaza en memoria."""
    comments = list(thread.comments.select_related("author").all())
    by_id = {c.pk: c for c in comments}
    roots = []
    for comment in comments:
        comment.children = []
        comment.can_delete = can_delete_comment(user, comment)
        comment.can_hard_delete = can_hard_delete_comment(user, comment)
    for comment in comments:
        if comment.parent_id and comment.parent_id in by_id:
            by_id[comment.parent_id].children.append(comment)
        else:
            roots.append(comment)
    return roots


def thread_list(request):
    threads = Thread.objects.select_related("author").annotate(comment_count=Count("comments"))
    paginator = Paginator(threads, 15)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "forum/list.html", {"page_obj": page})


def thread_detail(request, pk):
    thread = get_object_or_404(Thread.objects.select_related("author"), pk=pk)

    reply_form = None
    if request.user.is_authenticated:
        read, created = ThreadRead.objects.get_or_create(thread=thread, user=request.user)
        if not created:
            read.save()
        if request.method == "POST":
            if thread.is_locked:
                return HttpResponseForbidden("Este hilo está cerrado.")
            reply_form = ThreadCommentForm(request.POST)
            if reply_form.is_valid():
                comment = reply_form.save(commit=False)
                comment.thread = thread
                comment.author = request.user
                parent_id = request.POST.get("parent_id")
                if parent_id:
                    comment.parent = get_object_or_404(ThreadComment, pk=parent_id, thread=thread)
                comment.save()
                messages.success(request, "Respuesta publicada.")
                notify_user = comment.parent.author if comment.parent_id else thread.author
                if notify_user_id := getattr(notify_user, "pk", None):
                    if notify_user_id != request.user.pk:
                        send_push_to_user(
                            notify_user,
                            title="Nueva respuesta en el foro",
                            body=f"{request.user} ha respondido en «{thread.title}»",
                            url=reverse("forum:detail", args=[thread.pk]),
                        )
                return redirect("forum:detail", pk=thread.pk)
        else:
            reply_form = ThreadCommentForm()

    return render(request, "forum/detail.html", {
        "thread": thread,
        "roots": _build_comment_tree(thread, request.user),
        "reply_form": reply_form,
        "is_moderator": is_moderator(request.user),
        "can_moderate": can_moderate_thread(request.user),
    })


@login_required
def thread_create(request):
    if not can_post(request.user):
        raise Http404

    if request.method == "POST":
        form = ThreadForm(request.POST)
        if form.is_valid():
            thread = form.save(commit=False)
            thread.author = request.user
            thread.save()
            messages.success(request, "Hilo creado.")
            return redirect(thread.get_absolute_url())
    else:
        form = ThreadForm()

    return render(request, "forum/form.html", {"form": form})


@login_required
def comment_delete(request, pk):
    comment = get_object_or_404(ThreadComment, pk=pk)
    thread_id = comment.thread_id

    if comment.is_deleted:
        # Segundo "borrar" sobre un comentario que ya estaba oculto: solo
        # Gestor/Admin, y esta vez es definitivo (se borra de verdad).
        if not can_hard_delete_comment(request.user, comment):
            raise Http404
        if request.method == "POST":
            comment.delete()
            messages.success(request, "Comentario eliminado definitivamente.")
    else:
        if not can_delete_comment(request.user, comment):
            raise Http404
        if request.method == "POST":
            comment.is_deleted = True
            comment.body = ""
            comment.save(update_fields=["is_deleted", "body"])
            messages.success(request, "Comentario eliminado.")

    return redirect("forum:detail", pk=thread_id)


@login_required
def thread_toggle_lock(request, pk):
    thread = get_object_or_404(Thread, pk=pk)
    if not can_moderate_thread(request.user):
        raise Http404
    if request.method == "POST":
        thread.is_locked = not thread.is_locked
        thread.save(update_fields=["is_locked"])
        messages.success(request, "Hilo cerrado." if thread.is_locked else "Hilo reabierto.")
    return redirect("forum:detail", pk=thread.pk)


@login_required
def thread_delete(request, pk):
    thread = get_object_or_404(Thread, pk=pk)
    if not can_moderate_thread(request.user):
        raise Http404
    if request.method == "POST":
        thread.delete()
        messages.success(request, "Hilo eliminado.")
        return redirect("forum:list")
    return render(request, "forum/confirm_delete.html", {"thread": thread})
