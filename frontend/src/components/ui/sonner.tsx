import { Toaster as Sonner } from "sonner"

type ToasterProps = React.ComponentProps<typeof Sonner>

const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="dark"
      position="top-center"
      expand={true}
      richColors
      className="toaster group"
      toastOptions={{
        duration: 5000,
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-card group-[.toaster]:text-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg group-[.toaster]:rounded-xl group-[.toaster]:font-heading group-[.toaster]:text-sm",
          title: "group-[.toast]:font-bold group-[.toast]:text-base",
          description: "group-[.toast]:text-muted-foreground group-[.toast]:text-sm",
          actionButton:
            "group-[.toast]:bg-primary group-[.toast]:text-primary-foreground",
          cancelButton:
            "group-[.toast]:bg-muted group-[.toast]:text-muted-foreground",
          success: "group-[.toaster]:!bg-[hsl(145,80%,10%)] group-[.toaster]:!border-[hsl(145,80%,30%)]",
          error: "group-[.toaster]:!bg-[hsl(0,80%,10%)] group-[.toaster]:!border-[hsl(0,80%,30%)]",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
