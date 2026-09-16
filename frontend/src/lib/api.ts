import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor to add JWT token
api.interceptors.request.use(
  (config) => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("token");
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// Response interceptor for handling 401s
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      // Clear token and redirect to login
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);

// API Service Wrapper (Handles Mocks)
export const apiService = {
  auth: {
    login: async (credentials: any) => {
      const formData = new URLSearchParams();
      formData.append("username", credentials.username);
      formData.append("password", credentials.password);

      return api.post("/auth/login", formData, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
    },
  },
  patients: {
    getAll: async () => {
      return api.get("/records/patients/");
    },
    getHistory: async () => {
      return api.get("/records/patients/diagnosis-history");
    },
    getDiagnosisHistory: async (params?: Record<string, any>) => {
      return api.get("/records/patients/diagnosis-history", { params });
    },
    getById: async (id: string) => {
      return api.get(`/records/patients/${id}`);
    },
    create: async (data: {
      name: string;
      external_id?: string;
      age?: number;
      gender?: string;
    }) => {
      return api.post("/records/patients/", data);
    },
    deleteImage: async (imageId: string | number) => {
      return api.delete(`/records/images/${imageId}`);
    },
    getHistoryReport: async (patientId: string | number) => {
      return api.get(`/records/patients/${patientId}/history-report`);
    },
    regenerateHistoryReport: async (patientId: string | number) => {
      return api.post(
        `/records/patients/${patientId}/history-report/regenerate`,
      );
    },
    downloadHistoryReport: async (patientId: string | number) => {
      return api.get(`/records/patients/${patientId}/history-report/pdf`, {
        responseType: "blob",
      });
    },
  },
  analysis: {
    getResult: async (patientId: string) => {
      return api.get(`/records/analysis/${patientId}`);
    },
    getFullResult: async (patientId: string) => {
      return api.get(`/records/analysis/patient/${patientId}/full`);
    },
    getSurvivalCurve: async (patientId: string) => {
      return api.get(`/analytics/survival/${patientId}`);
    },
    getXaiOverlay: async (imageId: string) => {
      return api.get(`/records/analysis/${imageId}/xai-overlay`);
    },
    getImageResult: async (imageId: string | number) => {
      return api.get(`/records/analysis/image/${imageId}`);
    },
    explainClassificationXai: async (imageId: string | number) => {
      return api.post(
        `/records/analysis/image/${imageId}/explain/classification`,
      );
    },
    submitClassificationReview: async (
      imageId: string | number,
      payload: { expert_tumor_label: string; expert_comment?: string },
    ) => {
      return api.post(
        `/records/analysis/image/${imageId}/classification-review`,
        payload,
      );
    },
    downloadReport: async (imageId: string | number) => {
      return api.get(`/records/analysis/image/${imageId}/report`, {
        responseType: "blob",
      });
    },
    getDashboardStats: async () => {
      return api.get("/records/dashboard/stats");
    },
  },
  inference: {
    runMri: async (imageId: string | number) => {
      return api.post(`/inference/mri/${imageId}`);
    },
    runPrognosis: async (patientId: string | number) => {
      return api.post(`/inference/prognosis/${patientId}`);
    },
    getTask: async (taskId: string | number) => {
      return api.get(`/inference/tasks/${taskId}`);
    },
    waitForTask: async (
      taskId: string | number,
      intervalMs = 2000,
      timeoutMs = 600000,
      onProgress?: (percent: number, status: string) => void,
    ) => {
      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        const response = await api.get(`/inference/tasks/${taskId}`);
        const task = response.data;

        if (task.status === "done" || task.status === "completed") {
          return task;
        }

        if (task.status === "failed") {
          throw new Error(task.error_message || "AI task failed");
        }

        if (
          task.status === "processing" &&
          onProgress &&
          task.progress_percent !== null
        ) {
          onProgress(
            task.progress_percent,
            task.progress_status || "Đang xử lý...",
          );
        }

        await new Promise((resolve) => setTimeout(resolve, intervalMs));
      }

      throw new Error("Inference timeout");
    },
  },
  upload: {
    mri: async (patientId: string, file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return api.post(`/upload/mri/?patient_id=${patientId}`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
    },
    mriSeries: async (patientId: string, files: File[] | File) => {
      const formData = new FormData();
      if (Array.isArray(files)) {
        files.forEach((f) => formData.append("files", f));
      } else {
        // Assume it's a ZIP file
        formData.append("zip_file", files);
      }
      return api.post(
        `/upload/mri/series?patient_id=${encodeURIComponent(patientId)}`,
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
        },
      );
    },
    rna: async (patientId: string, file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return api.post(
        `/upload/rna/?patient_id=${encodeURIComponent(patientId)}`,
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
          timeout: 1200000,
        },
      );
    },
    clinical: async (patientId: string, data: any) => {
      return api.patch(`/records/patients/${patientId}/clinical`, data);
    },
    wsiSeries: async (patientId: string, files: File[] | File) => {
      const formData = new FormData();
      if (Array.isArray(files)) {
        files.forEach((f) => formData.append("files", f));
      } else {
        // Assume it's a ZIP file
        formData.append("zip_file", files);
      }
      return api.post(
        `/upload/wsi/series?patient_id=${encodeURIComponent(patientId)}`,
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
        },
      );
    },
  },
};
