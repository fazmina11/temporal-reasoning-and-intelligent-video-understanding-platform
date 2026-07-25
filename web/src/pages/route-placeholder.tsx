import { motion } from "framer-motion";
export function RoutePlaceholder({ name }: { name: string }) { return <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="min-h-[calc(100vh-4rem)]" aria-label={`${name} placeholder`} />; }
