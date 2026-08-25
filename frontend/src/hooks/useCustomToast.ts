import { useToastContext } from "@/components/ui/Toast";

export const useCustomToast = () => {
  const { showSuccessToast, showErrorToast, showWarningToast, showInfoToast } = useToastContext();

  return {
    showSuccessToast,
    showErrorToast,
    showWarningToast,
    showInfoToast,
  };
};

export default useCustomToast;
