import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableEmpty } from "./Table";
import Badge from "./Badge";

export default {
  title: "UI/Table",
  component: Table,
};

const sampleData = [
  { id: 1, sku: "FIL-PLA-BLK", name: "PLA Black 1kg", stock: 42, status: "active" },
  { id: 2, sku: "FIL-PET-WHT", name: "PETG White 1kg", stock: 7, status: "low" },
  { id: 3, sku: "FIL-ABS-RED", name: "ABS Red 1kg", stock: 0, status: "out" },
  { id: 4, sku: "FIL-TPU-BLU", name: "TPU Blue 500g", stock: 23, status: "active" },
];

const statusVariant = { active: "success", low: "warning", out: "danger" };
const statusLabel = { active: "In Stock", low: "Low Stock", out: "Out of Stock" };

export const Default = {
  render: () => (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>SKU</TableHead>
          <TableHead>Product</TableHead>
          <TableHead>Stock</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sampleData.map((item) => (
          <TableRow key={item.id}>
            <TableCell className="font-mono text-sm">{item.sku}</TableCell>
            <TableCell>{item.name}</TableCell>
            <TableCell>{item.stock}</TableCell>
            <TableCell>
              <Badge variant={statusVariant[item.status]}>{statusLabel[item.status]}</Badge>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  ),
};

export const Empty = {
  render: () => (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>SKU</TableHead>
          <TableHead>Product</TableHead>
          <TableHead>Stock</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableEmpty colSpan={4}>No items found. Try adjusting your filters.</TableEmpty>
      </TableBody>
    </Table>
  ),
};
