import { api } from "@/lib/api";
import type {
  NeuroCaseOption,
  NeuroCaseDetail,
  NeuroComment,
  NeuroFeedScope,
  NeuroPost,
  NeuroRoi,
  NeuroRoiComment,
  NeuroPostType,
  NeuroReactionType,
  NeuroDoctor,
  NeuroConversation,
  NeuroMessage,
  NeuroMessengerCase,
  NeuroReviewQueueItem,
} from "@/components/neuroboard/types";

export const neuroboardApi = {
  getFeed: (params: {
    scope?: NeuroFeedScope;
    postType?: NeuroPostType;
    cursor?: number;
    limit?: number;
  }) =>
    api.get<{ items: NeuroPost[]; next_cursor?: number | null }>(
      "/neuroboard/feed",
      {
        params: {
          scope: params.scope || "all",
          post_type: params.postType,
          cursor: params.cursor,
          limit: params.limit || 15,
        },
      },
    ),

  createPost: (payload: {
    postType: NeuroPostType;
    content: string;
    imageId?: number;
    files: File[];
  }) => {
    const formData = new FormData();
    formData.append("post_type", payload.postType);
    formData.append("content", payload.content);
    if (payload.imageId) formData.append("image_id", String(payload.imageId));
    payload.files.forEach((file) => formData.append("files", file));
    return api.post<NeuroPost>("/neuroboard/posts", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  deletePost: (postId: number) => api.delete(`/neuroboard/posts/${postId}`),

  setReaction: (postId: number, reactionType: NeuroReactionType) =>
    api.put<NeuroPost>(`/neuroboard/posts/${postId}/reaction`, {
      reaction_type: reactionType,
    }),

  removeReaction: (postId: number) =>
    api.delete<NeuroPost>(`/neuroboard/posts/${postId}/reaction`),

  savePost: (postId: number) =>
    api.put<NeuroPost>(`/neuroboard/posts/${postId}/save`),

  unsavePost: (postId: number) =>
    api.delete<NeuroPost>(`/neuroboard/posts/${postId}/save`),

  getComments: (postId: number) =>
    api.get<{ items: NeuroComment[] }>(`/neuroboard/posts/${postId}/comments`),

  createComment: (
    postId: number,
    payload: { content: string; parentId?: number },
  ) =>
    api.post<NeuroComment>(`/neuroboard/posts/${postId}/comments`, {
      content: payload.content,
      parent_id: payload.parentId,
    }),

  getCaseOptions: () =>
    api.get<{ items: NeuroCaseOption[] }>("/neuroboard/case-options"),

  getCaseDetail: (postId: number) =>
    api.get<NeuroCaseDetail>(`/neuroboard/posts/${postId}/case-detail`),

  createRoiComment: (
    postId: number,
    payload: {
      visualLabel: string;
      roi: NeuroRoi;
      content: string;
      replyToId?: number;
    },
  ) =>
    api.post<{ items: NeuroRoiComment[] }>(`/neuroboard/posts/${postId}/roi-comments`, {
      reply_to_id: payload.replyToId,
      visual_label: payload.visualLabel,
      x: payload.roi.x,
      y: payload.roi.y,
      width: payload.roi.width,
      height: payload.roi.height,
      content: payload.content,
    }),

  recallRoiComment: (postId: number, commentId: number) =>
    api.delete<NeuroRoiComment>(`/neuroboard/posts/${postId}/roi-comments/${commentId}`),

  getMe: () =>
    api.get<{ id: number; username: string; role: string }>("/neuroboard/me"),

  getDoctors: (q?: string) =>
    api.get<{ items: NeuroDoctor[] }>("/neuroboard/doctors", {
      params: { q },
    }),

  getConversation: (doctorId: number, search?: string) =>
    api.get<{ conversation: NeuroConversation; messages: NeuroMessage[] }>(
      `/neuroboard/messenger/conversations/${doctorId}`,
      { params: { search } },
    ),

  sendMessage: (
    doctorId: number,
    payload: {
      content?: string;
      caseImageId?: number;
      replyToId?: number;
      image?: File;
    },
  ) => {
    const formData = new FormData();
    formData.append("content", payload.content || "");
    if (payload.caseImageId) formData.append("case_image_id", String(payload.caseImageId));
    if (payload.replyToId) formData.append("reply_to_id", String(payload.replyToId));
    if (payload.image) formData.append("image", payload.image);
    return api.post<NeuroMessage>(
      `/neuroboard/messenger/conversations/${doctorId}/messages`,
      formData,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
  },

  openSecondOpinion: (requestId: number) =>
    api.post<{ id: number; status: string }>(`/neuroboard/second-opinions/${requestId}/open`),

  getReviewQueue: (scope?: string) =>
    api.get<{ items: NeuroReviewQueueItem[] }>("/neuroboard/review-queue", {
      params: { scope },
    }),

  getMyCases: () =>
    api.get<{ items: NeuroMessengerCase[] }>("/neuroboard/my-cases"),
};
