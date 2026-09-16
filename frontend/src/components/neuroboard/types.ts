export type NeuroPostType = "normal" | "clinical_case";
export type NeuroFeedScope = "all" | "mine" | "saved";
export type NeuroReactionType = "like" | "support" | "insightful" | "concern";

export type NeuroAuthor = {
  id: number;
  username: string;
};

export type NeuroAttachment = {
  id: number;
  content_type: string;
  original_name?: string | null;
  sort_order: number;
  url?: string | null;
};

export type ClinicalSummary = {
  image_id: number;
  ai_label?: string | null;
  confidence?: number | null;
  bbox_confidence?: number | null;
  class_probabilities?: number[] | null;
  risk_score?: number | null;
  risk_group?: string | null;
  no_tumor_detected: boolean;
};

export type ClinicalMedia = {
  mri_url?: string | null;
  visuals?: Array<{
    label: string;
    url: string;
  }>;
};

export type NeuroPost = {
  id: number;
  post_type: NeuroPostType;
  content?: string | null;
  anonymous_case_code?: string | null;
  author: NeuroAuthor;
  is_owner: boolean;
  patient_id?: number;
  patient_name?: string | null;
  patient_external_id?: string | null;
  clinical_summary?: ClinicalSummary | null;
  clinical_media?: ClinicalMedia | null;
  attachments: NeuroAttachment[];
  reaction_count: number;
  comment_count: number;
  viewer_reaction?: NeuroReactionType | null;
  viewer_saved: boolean;
  created_at: string;
  updated_at: string;
};

export type NeuroComment = {
  id: number;
  post_id: number;
  parent_id?: number | null;
  content: string;
  author: NeuroAuthor;
  created_at: string;
  replies?: NeuroComment[];
};

export type NeuroCaseOption = {
  image_id: number;
  patient_id: number;
  patient_name?: string | null;
  patient_external_id?: string | null;
  scan_date?: string | null;
  analysis_created_at?: string | null;
  ai_label?: string | null;
  confidence?: number | null;
  no_tumor_detected: boolean;
};

export type NeuroRoi = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type NeuroRoiComment = {
  id: number;
  post_id: number;
  reply_to_id?: number | null;
  visual_label?: string | null;
  roi?: NeuroRoi | null;
  content: string;
  is_ai: boolean;
  is_deleted: boolean;
  author: {
    id?: number | null;
    username: string;
  };
  created_at: string;
  deleted_at?: string | null;
};

export type NeuroCaseDetail = {
  post: NeuroPost;
  roi_comments: NeuroRoiComment[];
};

export type NeuroDoctor = {
  id: number;
  username: string;
  display_name: string;
  role?: string | null;
  is_online: boolean;
  last_active_at?: string | null;
  unread_count: number;
  conversation_id?: number | null;
  latest_message_at?: string | null;
};

export type NeuroMessengerCase = {
  case_id: number;
  image_id: number;
  patient_id: number;
  patient_name?: string | null;
  patient_external_id?: string | null;
  scan_date?: string | null;
  thumbnail_url?: string | null;
  ai_label?: string | null;
  confidence?: number | null;
  risk_score?: number | null;
  risk_group?: string | null;
  review_status?: string | null;
  second_opinion_status?: string | null;
  second_opinion_request_id?: number | null;
};

export type NeuroMessage = {
  id: number;
  conversation_id: number;
  sender: NeuroDoctor;
  is_mine: boolean;
  reply_to_id?: number | null;
  message_type: "text" | "image" | "case";
  content?: string | null;
  image_url?: string | null;
  image_original_name?: string | null;
  case?: NeuroMessengerCase | null;
  second_opinion?: {
    id: number;
    status: string;
    request_message?: string | null;
  } | null;
  created_at: string;
  read_at?: string | null;
};

export type NeuroConversation = {
  id: number;
  doctor: NeuroDoctor;
  created_at: string;
  updated_at: string;
};

export type NeuroReviewQueueItem = {
  id: string;
  queue_type: "my_review" | "second_opinion";
  status: string;
  priority?: string | null;
  deadline?: string | null;
  assigned_to?: number;
  request?: {
    id: number;
    from: NeuroDoctor;
    message?: string | null;
    created_at: string;
  } | null;
  case: NeuroMessengerCase;
};
