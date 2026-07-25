import { useForm, type UseFormProps, type FieldValues, type UseFormReturn } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";
export function useZodForm<TSchema extends z.ZodType<FieldValues>>(schema: TSchema, options?: Omit<UseFormProps<z.infer<TSchema>>, "resolver">): UseFormReturn<z.infer<TSchema>> { return useForm<z.infer<TSchema>>({ ...options, resolver: zodResolver(schema) }); }
